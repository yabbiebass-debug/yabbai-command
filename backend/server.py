from fastapi import FastAPI, APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os, logging, httpx, re, asyncio, time
from pathlib import Path
from pydantic import BaseModel
from typing import Optional, List, Any, Dict
from datetime import datetime, timezone, timedelta
from bson import ObjectId

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'yabbai')]

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="YABBAI API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

api_router = APIRouter(prefix="/api")

SOLANA_RPC = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

# ── In-memory cache ────────────────────────────────────────────────────────────
PRICE_CACHE: Dict[str, Any] = {}   # mint -> {price, ts}
BALANCE_CACHE: Dict[str, Any] = {} # owner -> {data, ts}
PRICE_TTL = 30   # seconds
BALANCE_TTL = 15  # seconds

# ── Helpers ───────────────────────────────────────────────────────────────────

def serialize(doc):
    if doc is None:
        return None
    doc = dict(doc)
    if '_id' in doc:
        doc['id'] = str(doc.pop('_id'))
    for k, v in doc.items():
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
        elif isinstance(v, ObjectId):
            doc[k] = str(v)
    return doc

def is_valid_base58(s: str) -> bool:
    return bool(s and re.match(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$', s))

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()

# ── Models ───────────────────────────────────────────────────────────────────

class TokenMintUpdate(BaseModel):
    mint: str
    decimals: Optional[int] = 6
    supply: Optional[str] = "1000000000"
    treasury: Optional[str] = None
    mainWallet: Optional[str] = None
    network: Optional[str] = "mainnet-beta"
    launchpad: Optional[str] = None
    tx: Optional[str] = None

class SettingsBody(BaseModel):
    treasury_wallet: Optional[str] = "7dzgCA8G55VytZ8PS1b99rbbctzCgJbnEoBEYBnn15YR"
    main_wallet: Optional[str] = ""
    rpc_url: Optional[str] = "https://api.mainnet-beta.solana.com"
    slippage_bps: Optional[int] = 50
    autopayout_threshold: Optional[float] = 25.0
    fee_buffer_sol: Optional[float] = 0.005
    auto_reinvest: Optional[bool] = True
    autonomy_level: Optional[int] = 75
    risk_appetite: Optional[int] = 40
    reinvest_rate: Optional[int] = 60
    self_improve: Optional[bool] = True
    alert_price_drop_pct: Optional[float] = 20.0
    alert_balance_low_sol: Optional[float] = 0.5
    custom_rpc_enabled: Optional[bool] = False
    demo_mode: Optional[bool] = False

class MissionBody(BaseModel):
    name: str
    mission_type: str
    autonomy: int
    risk: int
    reinvest: int
    self_improve: bool = True
    locked_values: List[str] = []
    plan: Optional[str] = None
    status: Optional[str] = "active"
    estimated_apy: Optional[int] = None

class TransactionBody(BaseModel):
    type: str
    amount_sol: float
    from_address: Optional[str] = None
    to_address: Optional[str] = None
    sig: Optional[str] = None
    status: Optional[str] = "confirmed"
    label: Optional[str] = None
    amount_usd: Optional[float] = None

class PriceSnapshotBody(BaseModel):
    mint: str
    price: float

class TreasurySnapshotBody(BaseModel):
    address: str
    balance_sol: float
    balance_usd: Optional[float] = None

class EventBody(BaseModel):
    text: str
    color: Optional[str] = ""
    category: Optional[str] = "system"

# ── Token Mint CRUD ──────────────────────────────────────────────────────────

@api_router.get("/token-mint")
async def get_token_mint():
    doc = await db.token_mint_config.find_one({}, {"_id": 0})
    return doc or {"configured": False}

@api_router.post("/token-mint")
async def save_token_mint(body: TokenMintUpdate):
    if not is_valid_base58(body.mint):
        raise HTTPException(400, "Invalid mint address format")
    doc = {
        "configured": True,
        "mint": body.mint, "decimals": body.decimals, "supply": body.supply,
        "treasury": body.treasury or "7dzgCA8G55VytZ8PS1b99rbbctzCgJbnEoBEYBnn15YR",
        "mainWallet": body.mainWallet or "",
        "network": body.network or "mainnet-beta",
        "launchpad": body.launchpad, "tx": body.tx,
        "launchedAt": utcnow(),
    }
    await db.token_mint_config.replace_one({}, doc, upsert=True)
    return doc

@api_router.delete("/token-mint")
async def delete_token_mint():
    await db.token_mint_config.delete_many({})
    return {"ok": True}

# ── Settings ───────────────────────────────────────────────────────────────────

@api_router.get("/settings")
async def get_settings():
    doc = await db.settings.find_one({}, {"_id": 0})
    if not doc:
        default = SettingsBody().dict()
        default["updated_at"] = utcnow()
        await db.settings.insert_one(default)
        return default
    return doc

@api_router.post("/settings")
async def save_settings(body: SettingsBody):
    doc = body.dict()
    doc["updated_at"] = utcnow()
    if doc.get("rpc_url") and doc["custom_rpc_enabled"]:
        global SOLANA_RPC
        SOLANA_RPC = doc["rpc_url"]
    await db.settings.replace_one({}, doc, upsert=True)
    return doc

# ── Missions ───────────────────────────────────────────────────────────────────

@api_router.get("/missions")
async def list_missions():
    docs = await db.missions.find({}, {"_id": 1, "name": 1, "mission_type": 1, "autonomy": 1,
                                       "risk": 1, "status": 1, "created_at": 1, "estimated_apy": 1}).to_list(50)
    return [serialize(d) for d in docs]

@api_router.post("/missions")
async def create_mission(body: MissionBody):
    doc = body.dict()
    doc["created_at"] = utcnow()
    doc["deployed_count"] = 0
    result = await db.missions.insert_one(doc)
    doc.pop("_id", None)  # Remove ObjectId before returning
    doc["id"] = str(result.inserted_id)
    return doc

@api_router.put("/missions/{mission_id}")
async def update_mission(mission_id: str, body: MissionBody):
    try:
        oid = ObjectId(mission_id)
    except Exception:
        raise HTTPException(400, "Invalid mission ID")
    update = body.dict()
    update["updated_at"] = utcnow()
    result = await db.missions.update_one({"_id": oid}, {"$set": update})
    if result.matched_count == 0:
        raise HTTPException(404, "Mission not found")
    return {"ok": True, "id": mission_id}

@api_router.delete("/missions/{mission_id}")
async def delete_mission(mission_id: str):
    try:
        oid = ObjectId(mission_id)
    except Exception:
        raise HTTPException(400, "Invalid mission ID")
    await db.missions.delete_one({"_id": oid})
    return {"ok": True}

# ── Transactions ─────────────────────────────────────────────────────────────

@api_router.get("/transactions")
async def list_transactions(limit: int = Query(50, le=200)):
    docs = await db.transactions.find({}).sort("created_at", -1).to_list(limit)
    return [serialize(d) for d in docs]

@api_router.post("/transactions")
async def record_transaction(body: TransactionBody):
    doc = body.dict()
    doc["created_at"] = utcnow()
    result = await db.transactions.insert_one(doc)
    doc.pop("_id", None)  # Remove ObjectId before returning
    doc["id"] = str(result.inserted_id)
    return doc

# ── Price history ────────────────────────────────────────────────────────────

@api_router.get("/price-history")
async def get_price_history(mint: str, limit: int = Query(100, le=500)):
    if not is_valid_base58(mint):
        return {"ok": False, "points": []}
    docs = await db.price_history.find({"mint": mint}).sort("ts", 1).to_list(limit)
    return {"ok": True, "points": [{"price": d["price"], "ts": d["ts"].isoformat() if isinstance(d["ts"], datetime) else d["ts"]} for d in docs]}

@api_router.post("/price-snapshot")
async def add_price_snapshot(body: PriceSnapshotBody):
    if not is_valid_base58(body.mint):
        raise HTTPException(400, "Invalid mint")
    doc = {"mint": body.mint, "price": body.price, "ts": datetime.now(timezone.utc)}
    await db.price_history.insert_one(doc)
    # Keep only last 500 per mint
    count = await db.price_history.count_documents({"mint": body.mint})
    if count > 500:
        oldest = await db.price_history.find({"mint": body.mint}).sort("ts", 1).limit(count - 500).to_list(count - 500)
        if oldest:
            ids = [d["_id"] for d in oldest]
            await db.price_history.delete_many({"_id": {"$in": ids}})
    return {"ok": True}

# ── Treasury snapshots ──────────────────────────────────────────────────────────

@api_router.get("/treasury-snapshots")
async def get_treasury_snapshots(limit: int = Query(100, le=500)):
    docs = await db.treasury_snapshots.find({}).sort("ts", 1).to_list(limit)
    return [{"balance_sol": d["balance_sol"], "balance_usd": d.get("balance_usd"), "address": d.get("address"), "ts": d["ts"].isoformat() if isinstance(d["ts"], datetime) else d["ts"]} for d in docs]

@api_router.post("/treasury-snapshot")
async def add_treasury_snapshot(body: TreasurySnapshotBody):
    doc = {"address": body.address, "balance_sol": body.balance_sol, "balance_usd": body.balance_usd, "ts": datetime.now(timezone.utc)}
    await db.treasury_snapshots.insert_one(doc)
    count = await db.treasury_snapshots.count_documents({})
    if count > 500:
        oldest = await db.treasury_snapshots.find({}).sort("ts", 1).limit(count - 500).to_list(count - 500)
        if oldest:
            await db.treasury_snapshots.delete_many({"_id": {"$in": [d["_id"] for d in oldest]}})
    return {"ok": True}

# ── Events log ───────────────────────────────────────────────────────────────────

@api_router.get("/events")
async def get_events(limit: int = Query(40, le=200)):
    docs = await db.events.find({}).sort("ts", -1).to_list(limit)
    return [{"id": str(d["_id"]), "text": d["text"], "color": d.get("color", ""), "category": d.get("category", "system"), "ts": d["ts"].isoformat() if isinstance(d["ts"], datetime) else d["ts"]} for d in docs]

@api_router.post("/events")
async def add_event(body: EventBody):
    doc = {"text": body.text, "color": body.color, "category": body.category, "ts": datetime.now(timezone.utc)}
    result = await db.events.insert_one(doc)
    count = await db.events.count_documents({})
    if count > 200:
        oldest = await db.events.find({}).sort("ts", 1).limit(count - 200).to_list(count - 200)
        if oldest:
            await db.events.delete_many({"_id": {"$in": [d["_id"] for d in oldest]}})
    return {"ok": True, "id": str(result.inserted_id)}

# ── Jupiter Price Proxy (with cache) ────────────────────────────────────────────

@api_router.get("/jupiter-price")
@limiter.limit("60/minute")
async def get_jupiter_price(request: Request, mint: str):
    if not mint or not is_valid_base58(mint):
        return {"ok": False, "price": None, "error": "Invalid mint address"}
    # Check cache
    cached = PRICE_CACHE.get(mint)
    if cached and (time.time() - cached["ts"]) < PRICE_TTL:
        return {"ok": True, "price": cached["price"], "mint": mint, "cached": True}
    try:
        async with httpx.AsyncClient(timeout=8.0) as h:
            resp = await h.get("https://api.jup.ag/price/v2", params={"ids": mint}, headers={"Accept": "application/json"})
            if resp.status_code == 200:
                data = resp.json()
                price_data = data.get("data", {}).get(mint, {})
                price = price_data.get("price")
                if price is not None:
                    p = float(price)
                    PRICE_CACHE[mint] = {"price": p, "ts": time.time()}
                    return {"ok": True, "price": p, "mint": mint, "cached": False}
                return {"ok": True, "price": None, "mint": mint}
            return {"ok": False, "price": None, "error": f"Jupiter {resp.status_code}"}
    except httpx.TimeoutException:
        if cached:
            return {"ok": True, "price": cached["price"], "mint": mint, "cached": True, "stale": True}
        return {"ok": False, "price": None, "error": "Jupiter API timeout"}
    except Exception as e:
        logger.error(f"Jupiter price error: {e}")
        return {"ok": False, "price": None, "error": str(e)}

# ── Solana Balance Proxy (with cache) ───────────────────────────────────────────

@api_router.get("/solana-balance")
@limiter.limit("30/minute")
async def get_solana_balance(request: Request, owner: str):
    if not owner or not is_valid_base58(owner):
        return {"ok": False, "error": "Invalid owner address"}
    cached = BALANCE_CACHE.get(owner)
    if cached and (time.time() - cached["ts"]) < BALANCE_TTL:
        return {**cached["data"], "cached": True}
    try:
        async with httpx.AsyncClient(timeout=10.0) as h:
            sol_r = await h.post(SOLANA_RPC, json={"jsonrpc":"2.0","id":1,"method":"getBalance","params":[owner]}, headers={"Content-Type":"application/json"})
            lamports = sol_r.json().get("result", {}).get("value", 0)
            sol = lamports / 1_000_000_000
            tok_r = await h.post(SOLANA_RPC, json={"jsonrpc":"2.0","id":2,"method":"getTokenAccountsByOwner","params":[owner,{"programId":"TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},{"encoding":"jsonParsed"}]}, headers={"Content-Type":"application/json"})
            tokens = []
            for acct in tok_r.json().get("result", {}).get("value", []):
                info = acct.get("account",{}).get("data",{}).get("parsed",{}).get("info",{})
                m = info.get("mint"); amt = info.get("tokenAmount",{}).get("uiAmount",0); dec = info.get("tokenAmount",{}).get("decimals",0)
                if m and amt is not None: tokens.append({"mint":m,"amount":amt,"decimals":dec})
            data = {"ok":True, "sol":sol, "tokens":tokens}
            BALANCE_CACHE[owner] = {"data": data, "ts": time.time()}
            return data
    except httpx.TimeoutException:
        if cached: return {**cached["data"], "cached":True, "stale":True}
        return {"ok":False, "sol":0, "tokens":[], "error":"RPC timeout"}
    except Exception as e:
        logger.error(f"Balance error: {e}")
        return {"ok":False, "sol":0, "tokens":[], "error":str(e)}

# ── Analytics aggregate ────────────────────────────────────────────────────────────

@api_router.get("/analytics")
async def get_analytics():
    """Aggregate key metrics for analytics dashboard"""
    tx_count = await db.transactions.count_documents({})
    mission_count = await db.missions.count_documents({})
    price_count = await db.price_history.count_documents({})
    snap_count = await db.treasury_snapshots.count_documents({})
    
    # Total SOL swept
    pipeline = [{"$match": {"type": "sweep", "status": "confirmed"}},
                {"$group": {"_id": None, "total": {"$sum": "$amount_sol"}}}]
    agg = await db.transactions.aggregate(pipeline).to_list(1)
    total_swept = agg[0]["total"] if agg else 0
    
    # Latest price
    latest_price = None
    if price_count > 0:
        doc = await db.price_history.find_one({}, sort=[("ts", -1)])
        if doc: latest_price = doc["price"]
    
    # Latest treasury balance
    latest_treasury = None
    if snap_count > 0:
        doc = await db.treasury_snapshots.find_one({}, sort=[("ts", -1)])
        if doc: latest_treasury = doc["balance_sol"]
    
    return {
        "tx_count": tx_count,
        "mission_count": mission_count,
        "price_points": price_count,
        "treasury_snapshots": snap_count,
        "total_swept_sol": total_swept,
        "latest_price": latest_price,
        "latest_treasury_sol": latest_treasury,
    }

# ── Health ───────────────────────────────────────────────────────────────────

@api_router.get("/")
async def root():
    return {"message": "YABBAI API running", "status": "ok", "version": "2.0"}

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
