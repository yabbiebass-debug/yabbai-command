from fastapi import FastAPI, APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, Query, Header
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os, logging, httpx, re, asyncio, time, secrets
from pathlib import Path
from pydantic import BaseModel
from typing import Optional, List, Any, Dict
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from revenue.system import RevenueSystem

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db_mongo = client[os.environ.get('DB_NAME', 'yabbai')]
db = db_mongo  # Alias for compatibility

# Initialize Revenue System
revenue_system = RevenueSystem(db_mongo)

# Import after revenue_system is created
from revenue.live_tracker import LiveTracker
from revenue.agents import AgentPool

live_tracker = LiveTracker(db_mongo, revenue_system)

# Initialize Multi-Agent System
agent_pool = AgentPool(
    db=db_mongo,
    revenue_system=revenue_system,
    min_agents_per_phase=1,
    max_agents_per_phase=15,
    target_agents_per_phase=10,
)

# Background task references
background_task = None
agent_pool_task = None

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

# WITHDRAWAL WHITELIST - Only these addresses can receive funds from the platform
AUTHORIZED_WITHDRAWAL_ADDRESSES = {
    "7ApE9ABS11vdQCSPiPikGHcMU2iF7sFqRdSQUX1cwD7Z",  # Main wallet
    "49nBAJdaTSUyNo5Uepb8HSGXxjX26Pd4x5sJp8PaNoFz",  # Secondary wallet
    "HTN1fvHwbzKiMwh9YXZEe3eooiMdoCAs3TweWdiSZV5i",  # Treasury wallet
}

def is_authorized_withdrawal_address(address: str) -> bool:
    """Check if an address is authorized to receive withdrawals/sweeps."""
    if not address:
        return False
    return address.strip() in AUTHORIZED_WITHDRAWAL_ADDRESSES

def validate_withdrawal_destination(address: str) -> None:
    """Validate withdrawal destination address. Raises HTTPException if not authorized."""
    if not is_authorized_withdrawal_address(address):
        raise HTTPException(
            status_code=403,
            detail=f"Unauthorized withdrawal address. Funds can only be sent to whitelisted addresses for security."
        )

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

# ── Sweep / Withdrawal Endpoints ────────────────────────────────────────────────

@api_router.post("/sweep")
@limiter.limit("10/minute")
async def log_sweep(request: Request):
    """Log a sweep/withdrawal transaction with destination validation."""
    try:
        data = await request.json()
        from_addr = data.get("from", "")
        to_addr = data.get("to", "")
        amount = data.get("amount_sol", 0)
        signature = data.get("signature", "")
        
        # CRITICAL: Validate destination is whitelisted
        validate_withdrawal_destination(to_addr)
        
        doc = {
            "type": "sweep",
            "from_address": from_addr,
            "to_address": to_addr,
            "amount_sol": amount,
            "signature": signature,
            "created_at": utcnow(),
        }
        await db.transactions.insert_one(doc)
        return {"ok": True, "message": "Sweep logged successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sweep logging error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/sweep/validate-destination")
async def validate_sweep_destination(address: str = Query(...)):
    """Validate if an address is authorized for withdrawals."""
    is_authorized = is_authorized_withdrawal_address(address)
    return {
        "authorized": is_authorized,
        "address": address,
        "message": "Address is authorized for withdrawals" if is_authorized else "Address is NOT authorized. Only whitelisted addresses can receive funds.",
        "whitelist": list(AUTHORIZED_WITHDRAWAL_ADDRESSES)
    }

# ── Health ───────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# REVENUE SYSTEM ROUTES
# ─────────────────────────────────────────────────────────────────────────────

REVENUE_ADMIN_KEY = os.getenv("REVENUE_ADMIN_KEY")

def verify_revenue_admin(authorization: Optional[str] = Header(None)):
    """Verify revenue admin key."""
    if not REVENUE_ADMIN_KEY:
        raise HTTPException(status_code=500, detail="Revenue admin key not configured")
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    # Support "Bearer <key>" or just "<key>"
    token = authorization.replace("Bearer ", "").strip()
    if token != REVENUE_ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Invalid revenue admin key")
    return True

@api_router.get("/revenue/dashboard")
async def revenue_dashboard():
    """Get complete revenue dashboard data."""
    try:
        data = await revenue_system.get_dashboard_data()
        return JSONResponse(content=data)
    except Exception as e:
        logger.error(f"Revenue dashboard error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/revenue/status")
async def revenue_status():
    """Get revenue system status (public)."""
    try:
        return {
            "real_income": revenue_system.ledger.real_income(),
            "net_profit": revenue_system.ledger.net_profit(),
            "gates": revenue_system.gates.status(),
            "channels": ["products", "agency", "trading"],
        }
    except Exception as e:
        logger.error(f"Revenue status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/revenue/approvals")
async def revenue_approvals(authorization: Optional[str] = Header(None)):
    """Get pending approvals queue (admin only)."""
    verify_revenue_admin(authorization)
    try:
        approvals = revenue_system.gates.pending_approvals()
        return {"ok": True, "approvals": approvals}
    except Exception as e:
        logger.error(f"Revenue approvals error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/revenue/actions/propose")
async def revenue_propose_action(
    request: Request,
    authorization: Optional[str] = Header(None)
):
    """Propose a new action."""
    verify_revenue_admin(authorization)
    try:
        data = await request.json()
        result = revenue_system.propose_action(data)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Revenue propose action error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/revenue/actions/approve/{queue_id}")
async def revenue_approve_action(
    queue_id: str,
    request: Request,
    authorization: Optional[str] = Header(None)
):
    """Approve a queued action."""
    verify_revenue_admin(authorization)
    try:
        data = await request.json()
        approver = data.get("approver", "admin")
        signature = data.get("signature")
        result = revenue_system.approve_action(queue_id, approver, signature)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Revenue approve action error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/revenue/actions/reject/{queue_id}")
async def revenue_reject_action(
    queue_id: str,
    request: Request,
    authorization: Optional[str] = Header(None)
):
    """Reject a queued action."""
    verify_revenue_admin(authorization)
    try:
        data = await request.json()
        approver = data.get("approver", "admin")
        reason = data.get("reason", "")
        result = revenue_system.reject_action(queue_id, approver, reason)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Revenue reject action error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/revenue/compliance/check")
async def revenue_check_compliance(request: Request):
    """Check text for compliance violations."""
    try:
        data = await request.json()
        text = data.get("text", "")
        context = data.get("context", "general")
        result = revenue_system.check_compliance(text, context)
        # Convert ComplianceResult to dict
        return {
            "ok": result.ok,
            "issues": result.issues,
            "requires_human": result.requires_human,
            "note": result.note,
        }
    except Exception as e:
        logger.error(f"Revenue compliance check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/revenue/kill-switch/engage")
async def revenue_engage_kill_switch(authorization: Optional[str] = Header(None)):
    """Engage the kill switch (halt all activity)."""
    verify_revenue_admin(authorization)
    try:
        result = revenue_system.engage_kill_switch()
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Revenue kill-switch engage error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/revenue/kill-switch/disengage")
async def revenue_disengage_kill_switch(authorization: Optional[str] = Header(None)):
    """Disengage the kill switch."""
    verify_revenue_admin(authorization)
    try:
        result = revenue_system.disengage_kill_switch()
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Revenue kill-switch disengage error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/revenue/caps/update")
async def revenue_update_caps(
    request: Request,
    authorization: Optional[str] = Header(None)
):
    """Update capital caps (can only tighten)."""
    verify_revenue_admin(authorization)
    try:
        data = await request.json()
        result = revenue_system.update_caps(data)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Revenue update caps error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/revenue/orchestrator/cycle")
async def revenue_run_cycle(authorization: Optional[str] = Header(None)):
    """Run one orchestrator cycle."""
    verify_revenue_admin(authorization)
    try:
        result = revenue_system.run_cycle()
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Revenue orchestrator cycle error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Webhooks (signed for production - basic version for now)
@api_router.post("/revenue/webhooks/product-sale")
async def revenue_webhook_product_sale(request: Request):
    """Product sale webhook (Stripe, Gumroad, etc.)."""
    try:
        data = await request.json()
        result = revenue_system.handle_product_sale(data)
        
        # Track in live system
        if result.get("ok"):
            await live_tracker.track_income(
                source="product_sale",
                amount=result.get("booked_usd", 0),
                data=data
            )
            await live_tracker.track_metric(result.get("metric", {}))
        
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Revenue product sale webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/revenue/webhooks/invoice-paid")
async def revenue_webhook_invoice_paid(request: Request):
    """Invoice paid webhook (for agency services)."""
    try:
        data = await request.json()
        result = revenue_system.handle_invoice_paid(data)
        
        # Track in live system
        if result.get("ok"):
            await live_tracker.track_income(
                source="invoice_paid",
                amount=result.get("booked_usd", 0),
                data=data
            )
            await live_tracker.track_metric(result.get("metric", {}))
        
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Revenue invoice paid webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/revenue/webhooks/sweep-attempted")
async def revenue_webhook_sweep_attempted(request: Request):
    """Track sweep attempt (for audit trail)."""
    try:
        data = await request.json()
        
        # Log sweep attempt
        await db.revenue_sweeps.insert_one({
            "from": data.get("from"),
            "to": data.get("to"),
            "token": data.get("token"),
            "amount": data.get("amount"),
            "status": "attempted",
            "timestamp": datetime.now(timezone.utc),
        })
        
        logger.info(f"💰 Sweep attempted: {data.get('amount')} {data.get('token')} → {data.get('to')}")
        
        return {"ok": True, "tracked": True}
    except Exception as e:
        logger.error(f"Sweep tracking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ── Live Tracking Endpoints ────────────────────────────────────────────────

@api_router.get("/revenue/live/status")
async def revenue_live_status():
    """Get live tracking status."""
    try:
        status = await live_tracker.get_live_status()
        return JSONResponse(content=status)
    except Exception as e:
        logger.error(f"Revenue live status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/revenue/live/dashboard")
async def revenue_live_dashboard():
    """Get complete live dashboard with real-time data."""
    try:
        dashboard = await live_tracker.get_live_dashboard()
        return JSONResponse(content=dashboard)
    except Exception as e:
        logger.error(f"Revenue live dashboard error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/revenue/live/metrics")
async def revenue_live_metrics(limit: int = 50):
    """Get live metrics stream."""
    try:
        metrics = await live_tracker.get_live_metrics(limit)
        return JSONResponse(content={"metrics": metrics, "count": len(metrics)})
    except Exception as e:
        logger.error(f"Revenue live metrics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/revenue/live/income")
async def revenue_live_income(limit: int = 100):
    """Get live income stream."""
    try:
        income = await live_tracker.get_live_income_stream(limit)
        total = sum(item.get("amount", 0) for item in income)
        return JSONResponse(content={
            "income": income,
            "count": len(income),
            "total": round(total, 2)
        })
    except Exception as e:
        logger.error(f"Revenue live income error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/revenue/live/start")
async def revenue_live_start(authorization: Optional[str] = Header(None)):
    """Manually start the live tracker (admin only)."""
    verify_revenue_admin(authorization)
    global background_task
    try:
        if not live_tracker.running:
            background_task = asyncio.create_task(live_tracker.start_background_orchestrator())
            return {"ok": True, "status": "started"}
        return {"ok": True, "status": "already_running"}
    except Exception as e:
        logger.error(f"Revenue live start error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/revenue/live/stop")
async def revenue_live_stop(authorization: Optional[str] = Header(None)):
    """Manually stop the live tracker (admin only)."""
    verify_revenue_admin(authorization)
    global background_task
    try:
        await live_tracker.stop_background_orchestrator()
        if background_task:
            background_task.cancel()
            background_task = None
        return {"ok": True, "status": "stopped"}
    except Exception as e:
        logger.error(f"Revenue live stop error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# WebSocket for live updates
@app.websocket("/ws/revenue/live")
async def revenue_live_websocket(websocket: WebSocket):
    """WebSocket endpoint for live revenue updates."""
    await websocket.accept()
    live_tracker.subscribe(websocket)
    
    try:
        # Send initial status
        status = await live_tracker.get_live_status()
        await websocket.send_json({
            "type": "connected",
            "data": status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        # Keep connection alive
        while True:
            # Ping every 30 seconds
            await asyncio.sleep(30)
            await websocket.send_json({
                "type": "ping",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
    except WebSocketDisconnect:
        live_tracker.unsubscribe(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        live_tracker.unsubscribe(websocket)

# ─────────────────────────────────────────────────────────────────────────────
# MULTI-AGENT SYSTEM ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@api_router.get("/agents/status")
async def agents_status():
    """Get multi-agent pool status."""
    try:
        status = agent_pool.get_status()
        return JSONResponse(content=status)
    except Exception as e:
        logger.error(f"Agents status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/agents/start")
async def agents_start(authorization: Optional[str] = Header(None)):
    """Start the agent pool (admin only)."""
    verify_revenue_admin(authorization)
    try:
        if not agent_pool.running:
            asyncio.create_task(agent_pool.start())
            return {"ok": True, "status": "started"}
        return {"ok": True, "status": "already_running"}
    except Exception as e:
        logger.error(f"Agents start error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/agents/stop")
async def agents_stop(authorization: Optional[str] = Header(None)):
    """Stop the agent pool (admin only)."""
    verify_revenue_admin(authorization)
    try:
        await agent_pool.stop()
        return {"ok": True, "status": "stopped"}
    except Exception as e:
        logger.error(f"Agents stop error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/agents/spawn/{phase}")
async def agents_spawn_phase(
    phase: str,
    authorization: Optional[str] = Header(None)
):
    """Spawn additional agent for a specific phase (admin only)."""
    verify_revenue_admin(authorization)
    try:
        from revenue.agents import Phase
        phase_enum = Phase(phase.lower())
        agent_id = await agent_pool.spawn_agent(phase_enum)
        
        if agent_id:
            return {"ok": True, "agent_id": agent_id, "phase": phase}
        else:
            return {"ok": False, "error": "Max agents reached for phase"}
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid phase: {phase}")
    except Exception as e:
        logger.error(f"Agents spawn error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/agents/phase/{phase}")
async def agents_phase_status(phase: str):
    """Get status for a specific phase."""
    try:
        from revenue.agents import Phase
        phase_enum = Phase(phase.lower())
        
        status = agent_pool.get_status()
        phase_data = status["phase_breakdown"].get(phase.lower(), {})
        
        return JSONResponse(content={
            "phase": phase,
            "data": phase_data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid phase: {phase}")
    except Exception as e:
        logger.error(f"Phase status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────────────────────────────────────
# Health / API Monitoring

@api_router.get("/health/details")
@limiter.limit("30/minute")
async def health_details(request: Request):
    """Return detailed health metrics for all backend integrations."""
    health_status = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": []
    }
    
    # MongoDB check
    try:
        start = time.time()
        await db_mongo.list_collection_names()
        latency_ms = int((time.time() - start) * 1000)
        health_status["services"].append({
            "id": "mongodb",
            "name": "MongoDB",
            "category": "Database",
            "status": "live",
            "latency": latency_ms,
            "url": "Internal MongoDB"
        })
    except Exception as e:
        health_status["services"].append({
            "id": "mongodb",
            "name": "MongoDB",
            "category": "Database",
            "status": "error",
            "latency": 0,
            "error": str(e),
            "url": "Internal MongoDB"
        })
    
    # Solana RPC check
    try:
        start = time.time()
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                SOLANA_RPC,
                json={"jsonrpc": "2.0", "id": 1, "method": "getHealth"}
            )
        latency_ms = int((time.time() - start) * 1000)
        health_status["services"].append({
            "id": "sol-rpc",
            "name": "Solana RPC",
            "category": "Chain",
            "status": "live" if resp.status_code == 200 else "error",
            "latency": latency_ms,
            "url": SOLANA_RPC
        })
    except Exception as e:
        health_status["services"].append({
            "id": "sol-rpc",
            "name": "Solana RPC",
            "category": "Chain",
            "status": "error",
            "latency": 0,
            "error": str(e),
            "url": SOLANA_RPC
        })
    
    # Jupiter check
    try:
        start = time.time()
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Just check if Jupiter API is reachable
            resp = await client.get("https://quote-api.jup.ag/v6/quote?inputMint=So11111111111111111111111111111111111111112&outputMint=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v&amount=1000000")
        latency_ms = int((time.time() - start) * 1000)
        health_status["services"].append({
            "id": "jup",
            "name": "Jupiter Price",
            "category": "DEX",
            "status": "live" if resp.status_code == 200 else "error",
            "latency": latency_ms,
            "url": "quote-api.jup.ag"
        })
    except Exception as e:
        health_status["services"].append({
            "id": "jup",
            "name": "Jupiter Price",
            "category": "DEX",
            "status": "error",
            "latency": 0,
            "error": str(e),
            "url": "quote-api.jup.ag"
        })
    
    # Revenue system check
    try:
        start = time.time()
        # Revenue system doesn't have get_status(), check if it's initialized instead
        status_data = revenue_system.ledger.summary()
        latency_ms = int((time.time() - start) * 1000)
        health_status["services"].append({
            "id": "revenue",
            "name": "Revenue System",
            "category": "Internal",
            "status": "live",
            "latency": latency_ms,
            "url": f"${status_data.get('real_income', 0):.2f} real income"
        })
    except Exception as e:
        health_status["services"].append({
            "id": "revenue",
            "name": "Revenue System",
            "category": "Internal",
            "status": "error",
            "latency": 0,
            "error": str(e),
            "url": "Internal Revenue System"
        })
    
    # Agent pool check
    try:
        start = time.time()
        agent_status = agent_pool.get_status()
        latency_ms = int((time.time() - start) * 1000)
        health_status["services"].append({
            "id": "agents",
            "name": "Agent Pool",
            "category": "Internal",
            "status": "live",
            "latency": latency_ms,
            "url": f"{agent_status['total_agents']} agents active"
        })
    except Exception as e:
        health_status["services"].append({
            "id": "agents",
            "name": "Agent Pool",
            "category": "Internal",
            "status": "error",
            "latency": 0,
            "error": str(e),
            "url": "Internal Agent Pool"
        })
    
    return JSONResponse(content=health_status)

# ─────────────────────────────────────────────────────────────────────────────

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

@app.on_event("startup")
async def startup_revenue_tracker():
    """Start the live revenue tracking and agent pool on startup."""
    global background_task, agent_pool_task
    try:
        # Start background orchestrator
        background_task = asyncio.create_task(live_tracker.start_background_orchestrator())
        logger.info("✅ Live Revenue Tracker started")

        # Start multi-agent pool
        agent_pool_task = asyncio.create_task(agent_pool.start())
        logger.info("✅ Multi-Agent Pool started")

    except Exception as e:
        logger.error(f"Failed to start systems: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    """Shutdown database and stop all systems."""
    global background_task, agent_pool_task
    try:
        await live_tracker.stop_background_orchestrator()
        if background_task:
            background_task.cancel()
        logger.info("⏸️  Live Revenue Tracker stopped")

        await agent_pool.stop()
        if agent_pool_task:
            agent_pool_task.cancel()
        logger.info("⏸️  Multi-Agent Pool stopped")

    except Exception as e:
        logger.error(f"Error stopping systems: {e}")
    client.close()
