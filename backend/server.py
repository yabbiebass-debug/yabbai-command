from fastapi import FastAPI, APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, Query, Header, Depends
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
from achievements import AchievementTracker
from solana_live import SolanaLive, jupiter_price as live_jupiter_price
from performance import treasury_performance
from dexscreener import market as dex_market, gaps as dex_gaps
from graduation import assess as grad_assess, summary_line as grad_summary
from revenue.ledger_store import (
    persist as ledger_persist,
    load_all as ledger_load_all,
    totals as ledger_totals,
    ensure_indexes as ledger_ensure_indexes,
)
from revenue.webhook_auth import (
    verify as wh_verify,
    configured_sources as wh_configured_sources,
)
import json

# Load environment BEFORE importing hub_sso (it reads HUB_AUTH_URL at import time)
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Hub SSO Integration
from hub_sso import router as sso_router, require_director

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db_mongo = client[os.environ.get('DB_NAME', 'yabbai')]
db = db_mongo  # Alias for compatibility

# Initialize Revenue System
revenue_system = RevenueSystem(db_mongo)

# Initialize Achievement Tracker
achievement_tracker = AchievementTracker(db_mongo)

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
snapshot_task = None

# How often to persist a real mainnet observation (seconds).
SNAPSHOT_INTERVAL = int(os.environ.get("SNAPSHOT_INTERVAL_SECONDS", "300"))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="YABBAI API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Mount Hub SSO Router
app.include_router(sso_router)

api_router = APIRouter(prefix="/api")

SOLANA_RPC = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

# Wrapped SOL, used to price the SOL side of the treasury so a token holding can
# be expressed in SOL without mixing units.
SOL_MINT = "So11111111111111111111111111111111111111112"

# Fallback endpoints, tried when the primary refuses a method on plan grounds.
# Chainstack's shared tier declines getProgramAccounts, getTokenLargestAccounts and
# getTokenAccountsByOwner, which blanks holder count, concentration and treasury
# token balance. Set SOLANA_RPC_FALLBACKS to a comma-separated list to override.
from solana_live import DEFAULT_FALLBACKS as _DEFAULT_RPC_FALLBACKS
SOLANA_FALLBACKS = [
    u.strip()
    for u in os.environ.get("SOLANA_RPC_FALLBACKS", ",".join(_DEFAULT_RPC_FALLBACKS)).split(",")
    if u.strip()
]

# ── In-memory cache ────────────────────────────────────────────────────────────
PRICE_CACHE: Dict[str, Any] = {}   # mint -> {price, ts}
BALANCE_CACHE: Dict[str, Any] = {} # owner -> {data, ts}
PRICE_TTL = 30   # seconds
BALANCE_TTL = 15  # seconds

# ── Helpers ───────────────────────────────────────────────────────────────────

# WITHDRAWAL WHITELIST - Only these addresses can receive funds from the platform
# Treasury wallet (source only - cannot receive sweeps)
TREASURY_WALLET = "HTN1fvHwbzKiMwh9YXZEe3eooiMdoCAs3TweWdiSZV5i"

# Authorized destinations for treasury sweeps (ONLY these two)
AUTHORIZED_WITHDRAWAL_ADDRESSES = {
    "7ApE9ABS11vdQCSPiPikGHcMU2iF7sFqRdSQUX1cwD7Z",  # METAMASK_MAIN WALLET
    "49nBAJdaTSUyNo5Uepb8HSGXxjX26Pd4x5sJp8PaNoFz",  # JUPITER_MAIN WALLET
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
async def get_token_mint(user: dict = Depends(require_director)):
    # Returns treasury and main wallet addresses — director only. Holders get the
    # mint address from /api/public/token instead.
    doc = await db.token_mint_config.find_one({}, {"_id": 0})
    return doc or {"configured": False}

@api_router.post("/token-mint")
async def save_token_mint(body: TokenMintUpdate, user: dict = Depends(require_director)):
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
async def delete_token_mint(user: dict = Depends(require_director)):
    await db.token_mint_config.delete_many({})
    return {"ok": True}

# ── Settings ───────────────────────────────────────────────────────────────────

@api_router.get("/settings")
async def get_settings(user: dict = Depends(require_director)):
    doc = await db.settings.find_one({}, {"_id": 0})
    if not doc:
        default = SettingsBody().dict()
        default["updated_at"] = utcnow()
        await db.settings.insert_one(default)
        return default
    return doc

@api_router.post("/settings")
async def save_settings(body: SettingsBody, user: dict = Depends(require_director)):
    doc = body.dict()
    doc["updated_at"] = utcnow()
    if doc.get("rpc_url") and doc["custom_rpc_enabled"]:
        global SOLANA_RPC
        SOLANA_RPC = doc["rpc_url"]
    await db.settings.replace_one({}, doc, upsert=True)
    return doc

# ── Missions ───────────────────────────────────────────────────────────────────

@api_router.get("/missions")
async def list_missions(user: dict = Depends(require_director)):
    docs = await db.missions.find({}, {"_id": 1, "name": 1, "mission_type": 1, "autonomy": 1,
                                       "risk": 1, "status": 1, "created_at": 1, "estimated_apy": 1}).to_list(50)
    return [serialize(d) for d in docs]

@api_router.post("/missions")
async def create_mission(body: MissionBody, user: dict = Depends(require_director)):
    doc = body.dict()
    doc["created_at"] = utcnow()
    doc["deployed_count"] = 0
    result = await db.missions.insert_one(doc)
    doc.pop("_id", None)  # Remove ObjectId before returning
    doc["id"] = str(result.inserted_id)
    return doc

@api_router.put("/missions/{mission_id}")
async def update_mission(mission_id: str, body: MissionBody, user: dict = Depends(require_director)):
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
async def delete_mission(mission_id: str, user: dict = Depends(require_director)):
    try:
        oid = ObjectId(mission_id)
    except Exception:
        raise HTTPException(400, "Invalid mission ID")
    await db.missions.delete_one({"_id": oid})
    return {"ok": True}

# ── Transactions ─────────────────────────────────────────────────────────────

@api_router.get("/transactions")
async def list_transactions(limit: int = Query(50, le=200),
                            user: dict = Depends(require_director)):
    docs = await db.transactions.find({}).sort("created_at", -1).to_list(limit)
    return [serialize(d) for d in docs]

@api_router.post("/transactions")
async def record_transaction(body: TransactionBody, user: dict = Depends(require_director)):
    doc = body.dict()
    doc["created_at"] = utcnow()
    result = await db.transactions.insert_one(doc)
    doc.pop("_id", None)  # Remove ObjectId before returning
    doc["id"] = str(result.inserted_id)
    return doc

# ── Price history ────────────────────────────────────────────────────────────

@api_router.get("/price-history")
async def get_price_history(mint: str, limit: int = Query(100, le=500),
                            user: dict = Depends(require_director)):
    if not is_valid_base58(mint):
        return {"ok": False, "points": []}
    docs = await db.price_history.find({"mint": mint}).sort("ts", 1).to_list(limit)
    return {"ok": True, "points": [{"price": d["price"], "ts": d["ts"].isoformat() if isinstance(d["ts"], datetime) else d["ts"]} for d in docs]}

@api_router.post("/price-snapshot")
async def add_price_snapshot(body: PriceSnapshotBody, user: dict = Depends(require_director)):
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
async def get_treasury_snapshots(limit: int = Query(100, le=500),
                                 user: dict = Depends(require_director)):
    docs = await db.treasury_snapshots.find({}).sort("ts", 1).to_list(limit)
    return [{"balance_sol": d["balance_sol"], "balance_usd": d.get("balance_usd"), "address": d.get("address"), "ts": d["ts"].isoformat() if isinstance(d["ts"], datetime) else d["ts"]} for d in docs]

@api_router.post("/treasury-snapshot")
async def add_treasury_snapshot(body: TreasurySnapshotBody, user: dict = Depends(require_director)):
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
async def get_events(limit: int = Query(40, le=200),
                     user: dict = Depends(require_director)):
    docs = await db.events.find({}).sort("ts", -1).to_list(limit)
    return [{"id": str(d["_id"]), "text": d["text"], "color": d.get("color", ""), "category": d.get("category", "system"), "ts": d["ts"].isoformat() if isinstance(d["ts"], datetime) else d["ts"]} for d in docs]

@api_router.post("/events")
async def add_event(body: EventBody, user: dict = Depends(require_director)):
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
    
    # Get Jupiter API key from environment
    jupiter_api_key = os.environ.get("JUPITER_API_KEY", "")
    headers = {"Accept": "application/json"}
    if jupiter_api_key:
        headers["x-api-key"] = jupiter_api_key
    
    try:
        async with httpx.AsyncClient(timeout=8.0) as h:
            resp = await h.get("https://api.jup.ag/price/v3", params={"ids": mint}, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                # v3 format: {mint: {usdPrice: ...}} instead of {data: {mint: {price: ...}}}
                price_data = data.get(mint, {})
                price = price_data.get("usdPrice") or price_data.get("price")
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
async def get_analytics(user: dict = Depends(require_director)):
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

# ── Live mainnet token stats ───────────────────────────────────────────────────

def _rpc_host(url: str) -> str:
    """Host only. RPC provider URLs embed the API key in the path or query, so the
    full string must never reach a response body, a log line, or the client."""
    try:
        return url.split("://", 1)[1].split("/", 1)[0].split("?", 1)[0]
    except (IndexError, AttributeError):
        return "unknown"


async def _configured_mint() -> Optional[str]:
    """Mint address, from env first then the database.

    A fresh deployment has an empty database, so requiring the mint to be seeded
    there means the public endpoints report `configured: false` until someone
    writes a row — through a director-only route they cannot reach yet. Reading
    TOKEN_MINT from the environment makes a deployment self-configuring, while the
    database still wins nothing and loses nothing for existing installs.
    """
    env_mint = (os.environ.get("TOKEN_MINT") or "").strip()
    if env_mint and is_valid_base58(env_mint):
        return env_mint

    doc = await db.token_mint_config.find_one({})
    mint = (doc or {}).get("mint")
    return mint if mint and is_valid_base58(mint) else None


async def _configured_treasury() -> str:
    env_treasury = (os.environ.get("TREASURY_WALLET") or "").strip()
    if env_treasury and is_valid_base58(env_treasury):
        return env_treasury

    doc = await db.settings.find_one({})
    return (doc or {}).get("treasury_wallet") or TREASURY_WALLET


@api_router.get("/token-stats")
@limiter.limit("30/minute")
async def get_token_stats(request: Request, user: dict = Depends(require_director)):
    """Live mainnet facts about the configured token — director view.

    The anonymous equivalent is /api/public/token, which returns a narrower
    whitelisted payload. This one may carry operational detail, so it is gated.

    Every field is read from chain or from Jupiter. Anything unavailable comes back
    as null with a matching entry in `data_gaps` — never as 0 and never estimated.
    """
    mint = await _configured_mint()
    if not mint:
        return {
            "ok": False,
            "configured": False,
            "detail": "No token mint configured. Set one in Settings.",
        }

    chain = SolanaLive(SOLANA_RPC, fallbacks=SOLANA_FALLBACKS)
    treasury_addr = await _configured_treasury()

    supply, authorities, largest, holders, price, treasury = await asyncio.gather(
        chain.token_supply(mint),
        chain.mint_authorities(mint),
        chain.largest_accounts(mint),
        chain.holder_count(mint),
        live_jupiter_price(mint, os.environ.get("JUPITER_API_KEY", "")),
        chain.treasury_state(treasury_addr, mint),
    )

    data_gaps: List[str] = []
    if supply is None:
        data_gaps.append("supply")
    if authorities is None:
        data_gaps.append("mint_authorities")
    if largest is None:
        data_gaps.append("largest_accounts")
    if holders is None:
        data_gaps.append("holder_count")
    if price is None:
        data_gaps.append("price")
    if treasury.get("sol") is None:
        data_gaps.append("treasury_sol")

    market_cap = None
    if supply and price is not None and supply.get("supply") is not None:
        market_cap = supply["supply"] * price

    # Share of supply held by the top accounts the RPC returned. A real, checkable
    # concentration measure — high values mean a few wallets can move the price.
    top_concentration_pct = None
    if largest and supply and supply.get("supply"):
        top_sum = sum(a["amount"] for a in largest if a.get("amount"))
        if supply["supply"] > 0:
            top_concentration_pct = round(top_sum / supply["supply"] * 100, 4)

    treasury_value_usd = None
    if price is not None and treasury.get("token_balance") is not None:
        treasury_value_usd = treasury["token_balance"] * price

    return {
        "ok": True,
        "configured": True,
        "mint": mint,
        "network": "mainnet-beta",
        # Never return SOLANA_RPC. Provider URLs carry the API key in the path or
        # query string, so echoing it here published the credential on an
        # unauthenticated endpoint. Expose only the host, which is not a secret.
        "rpc_host": _rpc_host(SOLANA_RPC),
        "supply": supply,
        "authorities": authorities,
        "holders": holders,
        "price_usd": price,
        "market_cap_usd": market_cap,
        "top_accounts": largest,
        "top_concentration_pct": top_concentration_pct,
        "treasury": treasury,
        "treasury_token_value_usd": treasury_value_usd,
        "data_gaps": data_gaps,
        "fetched_at": utcnow(),
    }


# ── Public (holders) surface ───────────────────────────────────────────────────
#
# Everything below is deliberately unauthenticated and is the ONLY unauthenticated
# data in the app. Two rules govern it:
#
#   1. Nothing here is secret. Every field is already readable by anyone with an
#      RPC endpoint and the mint address, so publishing it discloses nothing new.
#      Supply, price, holder count and authority status are public chain facts.
#   2. Payloads are built field by field. Never spread a Mongo document or an
#      internal dict into a public response — that is how a field added later
#      leaks without anyone noticing. If a new field belongs here, add it here
#      explicitly.
#
# Operational state — settings, transactions, sweeps, revenue, agents, health —
# is NOT public and must stay behind require_director.

@api_router.get("/public/token")
@limiter.limit("60/minute")
async def public_token(request: Request):
    """On-chain facts about the token. Safe for anonymous holders."""
    mint = await _configured_mint()
    if not mint:
        return {"ok": False, "configured": False}

    chain = SolanaLive(SOLANA_RPC, fallbacks=SOLANA_FALLBACKS)
    treasury_addr = await _configured_treasury()

    supply, authorities, largest, holders, price, treasury, mkt = await asyncio.gather(
        chain.token_supply(mint),
        chain.mint_authorities(mint),
        chain.largest_accounts(mint),
        chain.holder_count(mint),
        live_jupiter_price(mint, os.environ.get("JUPITER_API_KEY", "")),
        chain.treasury_state(treasury_addr, mint),
        dex_market(mint),
    )

    data_gaps: List[str] = []
    if supply is None:
        data_gaps.append("supply")
    if holders is None:
        data_gaps.append("holder_count")
    if largest is None:
        data_gaps.append("concentration")
    if price is None:
        data_gaps.append("price")
    if authorities is None:
        data_gaps.append("authorities")
    data_gaps.extend(dex_gaps(mkt))
    if treasury.get("sol") is None:
        data_gaps.append("treasury_sol")
    # holdings is None when the read failed; an empty list means genuinely no tokens.
    # Those are different facts and must not both render as a blank.
    if treasury.get("holdings") is None:
        data_gaps.append("treasury_token_balance")

    market_cap = None
    if supply and price is not None and supply.get("supply") is not None:
        market_cap = supply["supply"] * price

    concentration = None
    if largest and supply and supply.get("supply"):
        top_sum = sum(a["amount"] for a in largest if a.get("amount"))
        if supply["supply"] > 0:
            concentration = round(top_sum / supply["supply"] * 100, 4)

    return {
        "ok": True,
        "configured": True,
        "mint": mint,
        "network": "mainnet-beta",
        "supply": (supply or {}).get("supply"),
        "decimals": (supply or {}).get("decimals"),
        "price_usd": price,
        "market_cap_usd": market_cap,
        "holders": (holders or {}).get("holders"),
        "top_concentration_pct": concentration,
        # Verifiable trust signals — holders can check both against any explorer.
        "mint_authority_revoked": (authorities or {}).get("mint_revoked"),
        "freeze_authority_revoked": (authorities or {}).get("freeze_revoked"),
        # The treasury address is public by definition; publishing its balance is
        # the point of a transparent treasury.
        "treasury_address": treasury_addr,
        "treasury_sol": treasury.get("sol"),
        "treasury_token_balance": treasury.get("token_balance"),
        # Distance to graduation, measured. Until the curve completes there is no
        # liquidity pool and no LP fee share, so this is the number that matters
        # most to a holder deciding whether the project is going anywhere.
        "graduation": grad_assess(
            market_cap,
            await live_jupiter_price(SOL_MINT, os.environ.get("JUPITER_API_KEY", "")),
            (mkt or {}).get("volume_24h_usd"),
        ),
        # Traded activity. Chain reads cannot supply these; they come from
        # DexScreener. Fields absent while the token is on a bonding curve stay
        # null so the UI shows DATA GAP rather than claiming zero liquidity.
        "market": mkt,
        "data_gaps": data_gaps,
        "fetched_at": utcnow(),
    }


@api_router.get("/public/price-history")
@limiter.limit("60/minute")
async def public_price_history(request: Request, limit: int = Query(100, le=500)):
    """Recorded price series for the configured mint. Price is a public fact."""
    mint = await _configured_mint()
    if not mint:
        return {"ok": False, "configured": False, "points": []}
    docs = await db.price_history.find({"mint": mint}).sort("ts", 1).to_list(limit)
    return {
        "ok": True,
        "mint": mint,
        "points": [
            {
                "price": d["price"],
                "ts": d["ts"].isoformat() if isinstance(d["ts"], datetime) else d["ts"],
            }
            for d in docs
        ],
    }


@api_router.get("/ai/status")
async def ai_status(user: dict = Depends(require_director)):
    """Whether the hub AI gateway is reachable from this service."""
    from hub_ai import available
    return await available()


@api_router.post("/ai/ask")
@limiter.limit("20/minute")
async def ai_ask(request: Request, user: dict = Depends(require_director)):
    """Ask the hub's provider chain a question, grounded in system knowledge.

    The grounding is what keeps generated text from reinventing the fictions this
    project removed. Output is checked against the same rules before it is
    returned, and violations are reported rather than silently passed on.
    """
    from hub_ai import chat, HubAIError, HubAIUnavailable
    from knowledge import system_prompt, check_output

    data = await request.json()
    question = (data.get("question") or "").strip()
    if not question:
        raise HTTPException(400, "question is required")

    # Anchor the model to current chain state so it cannot invent figures.
    live: Dict[str, Any] = {}
    try:
        mint = await _configured_mint()
        if mint:
            chain = SolanaLive(SOLANA_RPC, fallbacks=SOLANA_FALLBACKS)
            supply, price = await asyncio.gather(
                chain.token_supply(mint),
                live_jupiter_price(mint, os.environ.get("JUPITER_API_KEY", "")),
            )
            live = {
                "price_usd": price,
                "market_cap_usd": (supply["supply"] * price)
                if supply and price is not None else None,
            }
    except Exception as e:
        logger.warning(f"ai_ask could not load live stats: {e}")

    try:
        answer = await chat([
            {"role": "system", "content": system_prompt(live)},
            {"role": "user", "content": question},
        ])
    except HubAIUnavailable as e:
        raise HTTPException(503, f"AI gateway not configured: {e}")
    except HubAIError as e:
        raise HTTPException(502, f"AI gateway error: {e}")

    issues = check_output(answer)
    return {
        "ok": True,
        "answer": answer,
        # Surfaced, not suppressed: a grounding violation is worth seeing.
        "grounding_issues": issues,
        "grounded_on": list(live.keys()),
    }


@api_router.post("/wallet/nonce")
@limiter.limit("30/minute")
async def wallet_nonce(request: Request, user: dict = Depends(require_director)):
    """Issue a single-use nonce and the exact text for the wallet to sign."""
    from wallet_auth import issue_nonce
    data = {}
    try:
        data = await request.json()
    except Exception:
        pass
    address = (data.get("address") or "").strip() or None
    if address and not is_valid_base58(address):
        raise HTTPException(400, "address is not valid base58")
    return {"ok": True, **issue_nonce(address)}


@api_router.post("/wallet/verify")
@limiter.limit("30/minute")
async def wallet_verify(request: Request, user: dict = Depends(require_director)):
    """Verify a signed message and record the wallet as proven.

    Signing proves control of the wallet. It authorises no transaction and moves
    no funds - it is an ed25519 signature over text this server issued. Director
    access is still hub SSO; this is a separate, narrower claim.
    """
    from wallet_auth import verify

    data = await request.json()
    address = (data.get("address") or "").strip()
    message = data.get("message") or ""
    signature = data.get("signature") or ""

    if not address or not message or not signature:
        raise HTTPException(400, "address, message and signature are required")

    ok, reason = verify(address, message, signature)
    if not ok:
        logger.warning(f"wallet verification failed for {address[:8]}...: {reason}")
        raise HTTPException(401, f"verification failed: {reason}")

    await db.verified_wallets.update_one(
        {"address": address},
        {"$set": {
            "address": address,
            "label": (data.get("label") or "").strip()[:40] or None,
            "verified_at": utcnow(),
            "verified_by": (user or {}).get("email"),
        }},
        upsert=True,
    )
    logger.info(f"wallet verified: {address[:8]}...")
    return {"ok": True, "address": address, "verified": True, "detail": reason}


@api_router.get("/wallet/verified")
async def wallet_verified(user: dict = Depends(require_director)):
    """Wallets that have proven control by signing."""
    docs = await db.verified_wallets.find({}, {"_id": 0}).to_list(50)
    return {"ok": True, "wallets": docs, "count": len(docs)}


@api_router.post("/buyback/quote")
@limiter.limit("30/minute")
async def buyback_quote(request: Request, user: dict = Depends(require_director)):
    """Price a treasury buyback and state what it would achieve.

    Quotes and proposes; it does not execute. Executing needs a signature, a
    signature needs a key, and a key on this server is what allowed the sweep
    that prompted this rebuild. Sign in your own wallet or use the Jupiter link.
    """
    from buyback import quote as bb_quote, plan as bb_plan

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    mint = await _configured_mint()
    if not mint:
        raise HTTPException(400, "no token mint configured")

    treasury_addr = await _configured_treasury()
    settings = await db.settings.find_one({}) or {}
    slippage_bps = int(body.get("slippage_bps") or settings.get("slippage_bps") or 50)

    chain = SolanaLive(SOLANA_RPC, fallbacks=SOLANA_FALLBACKS)
    state = await chain.treasury_state(treasury_addr, mint)
    treasury_sol = state.get("sol")

    # Default to spending most of what is spendable, leaving the fee reserve.
    from buyback import FEE_RESERVE_SOL
    requested = body.get("amount_sol")
    if requested is None:
        requested = max(0.0, (treasury_sol or 0.0) - FEE_RESERVE_SOL)
    amount_sol = float(requested)

    supply = await chain.token_supply(mint)
    decimals = (supply or {}).get("decimals", 6)

    q = await bb_quote(mint, amount_sol, slippage_bps,
                       os.environ.get("JUPITER_API_KEY", "")) if amount_sol > 0 else None

    price = await live_jupiter_price(mint, os.environ.get("JUPITER_API_KEY", ""))
    sol_price = await live_jupiter_price(SOL_MINT, os.environ.get("JUPITER_API_KEY", ""))
    mcap = (supply["supply"] * price) if supply and price is not None else None
    grad = grad_assess(mcap, sol_price)

    result = bb_plan(treasury_sol, q, decimals, amount_sol, grad)

    # Deep link so the operator can execute in Jupiter with the same parameters.
    if result.get("available"):
        result["jupiter_url"] = (
            f"https://jup.ag/swap/{SOL_MINT}-{mint}"
            f"?inAmount={amount_sol}&slippageBps={slippage_bps}"
        )
    return {"ok": True, "mint": mint, "treasury": treasury_addr, **result}


@api_router.post("/buyback/transaction")
@limiter.limit("20/minute")
async def buyback_transaction(request: Request, user: dict = Depends(require_director)):
    """Build an unsigned swap transaction for the operator's wallet to sign.

    The returned transaction is inert without a signature, and the only key that
    can sign it belongs to the wallet whose public key was supplied. This service
    holds no keys, cannot sign, and cannot submit. The operator approves it in
    their own wallet, which displays the amounts before they accept.
    """
    from buyback import quote as bb_quote, build_transaction

    body = await request.json()
    wallet = (body.get("wallet") or "").strip()
    amount_sol = float(body.get("amount_sol") or 0)

    if not wallet or not is_valid_base58(wallet):
        raise HTTPException(400, "a valid wallet public key is required")
    if amount_sol <= 0:
        raise HTTPException(400, "amount_sol must be greater than zero")

    mint = await _configured_mint()
    if not mint:
        raise HTTPException(400, "no token mint configured")

    settings = await db.settings.find_one({}) or {}
    slippage_bps = int(body.get("slippage_bps") or settings.get("slippage_bps") or 50)
    api_key = os.environ.get("JUPITER_API_KEY", "")

    q = await bb_quote(mint, amount_sol, slippage_bps, api_key)
    if not q:
        raise HTTPException(
            502, "no route quoted; the pool may be too thin for this size"
        )

    built = await build_transaction(q["raw"], wallet, api_key)
    if not built:
        raise HTTPException(502, "Jupiter could not build the transaction")

    # Record the intent. A proposal that is never signed leaves a trail showing
    # what was considered, which matters when reconciling treasury movement.
    await db.buyback_proposals.insert_one({
        "wallet": wallet,
        "mint": mint,
        "amount_sol": amount_sol,
        "slippage_bps": slippage_bps,
        "price_impact_pct": q["price_impact_pct"],
        "quoted_out_raw": q["out_amount_raw"],
        "proposed_by": (user or {}).get("email"),
        "proposed_at": utcnow(),
        "executed": False,
    })

    return {
        "ok": True,
        "mint": mint,
        "amount_sol": amount_sol,
        "price_impact_pct": round(q["price_impact_pct"], 4),
        **built,
    }


@api_router.post("/buyback/confirm")
@limiter.limit("20/minute")
async def buyback_confirm(request: Request, user: dict = Depends(require_director)):
    """Record a buyback the operator signed and submitted.

    The signature is the operator's proof it happened; this only records it so
    treasury movement can be reconciled later. It books no income: buying your
    own token converts SOL into tokens, which is a change of position, not
    revenue.
    """
    body = await request.json()
    signature = (body.get("signature") or "").strip()
    if not signature:
        raise HTTPException(400, "transaction signature is required")

    doc = {
        "type": "buyback",
        "signature": signature,
        "wallet": (body.get("wallet") or "").strip() or None,
        "amount_sol": body.get("amount_sol"),
        "tokens_out": body.get("tokens_out"),
        "confirmed_by": (user or {}).get("email"),
        "created_at": utcnow(),
        "explorer": f"https://solscan.io/tx/{signature}",
    }
    await db.transactions.insert_one(doc)
    await db.buyback_proposals.update_one(
        {"wallet": doc["wallet"], "executed": False},
        {"$set": {"executed": True, "signature": signature}},
        sort=[("proposed_at", -1)],
    )
    logger.info(f"buyback recorded: {signature[:16]}...")
    return {"ok": True, "signature": signature, "explorer": doc["explorer"]}


@api_router.get("/wallets")
async def get_wallets(user: dict = Depends(require_director)):
    """Live SOL and token balances for every configured wallet.

    Reads whatever addresses are configured, in one pass, from chain. There is no
    MetaMask entry: MetaMask is an Ethereum wallet and holds no SOL or SPL
    tokens, so labelling a Solana address as one would be wrong on the page. Any
    Solana address can be added under `extra_wallets` and it is read the same way.

    Read-only. This holds no keys and cannot move anything; spending still
    requires the operator's own wallet to sign, to an allowlisted destination.
    """
    settings = await db.settings.find_one({}) or {}
    mint = await _configured_mint()

    wallets = []
    treasury = await _configured_treasury()
    if treasury:
        wallets.append({"label": "Treasury", "address": treasury, "role": "treasury"})

    main = (os.environ.get("MAIN_WALLET") or settings.get("main_wallet") or "").strip()
    if main and is_valid_base58(main):
        wallets.append({"label": "Main", "address": main, "role": "main"})

    # Comma-separated "Label:Address" pairs, or bare addresses.
    for entry in (os.environ.get("EXTRA_WALLETS") or settings.get("extra_wallets") or "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        label, _, addr = entry.rpartition(":")
        addr = addr.strip()
        if is_valid_base58(addr):
            wallets.append({
                "label": (label.strip() or addr[:4] + "..." + addr[-4:]),
                "address": addr,
                "role": "extra",
            })

    if not wallets:
        return {
            "ok": True,
            "wallets": [],
            "detail": "No wallets configured. Set treasury_wallet or main_wallet "
                      "in Settings, or EXTRA_WALLETS as Label:Address pairs.",
        }

    chain = SolanaLive(SOLANA_RPC, fallbacks=SOLANA_FALLBACKS)
    price = await live_jupiter_price(mint, os.environ.get("JUPITER_API_KEY", "")) if mint else None

    states = await asyncio.gather(
        *[chain.treasury_state(w["address"], mint) for w in wallets],
        return_exceptions=True,
    )

    out = []
    for w, state in zip(wallets, states):
        if isinstance(state, Exception):
            out.append({**w, "sol": None, "token_balance": None,
                        "error": str(state)[:120]})
            continue
        token_balance = state.get("token_balance")
        out.append({
            **w,
            "sol": state.get("sol"),
            "token_balance": token_balance,
            "token_value_usd": token_balance * price
            if price is not None and token_balance is not None else None,
            "explorer": f"https://solscan.io/account/{w['address']}",
        })

    total_sol = sum(w["sol"] for w in out if isinstance(w.get("sol"), (int, float)))
    total_tokens = sum(
        w["token_balance"] for w in out
        if isinstance(w.get("token_balance"), (int, float))
    )

    return {
        "ok": True,
        "mint": mint,
        "price_usd": price,
        "wallets": out,
        "totals": {
            "sol": round(total_sol, 9),
            "token_balance": total_tokens,
            "token_value_usd": total_tokens * price if price is not None else None,
            # Only wallets that answered are summed; a failed read is excluded
            # rather than counted as zero.
            "wallets_read": sum(1 for w in out if w.get("sol") is not None),
            "wallets_total": len(out),
        },
        "fetched_at": utcnow(),
    }


@api_router.get("/yield")
async def get_yield(window_days: int = Query(30, ge=1, le=365),
                    user: dict = Depends(require_director)):
    """Everything that constitutes yield for this token, measured.

    Four separate things get conflated as "yield", so this reports them apart:

      treasury_performance  realised change with external flows backed out.
                            Depositing SOL is not a gain.
      treasury_now          current composition. A position, not a profit.
      booked_revenue        reconciled payment-processor income from the truth
                            ledger. The only figure that is actually income.
      token_trend           measured movement in price, holders and volume from
                            the agents' stored measurements.

    Anything without enough history returns available:false with a reason rather
    than a zero, because zero and unknown are different claims.
    """
    perf = await treasury_performance(db, window_days=window_days)
    booked = await ledger_totals(db)

    # Current treasury composition, read live.
    mint = await _configured_mint()
    treasury_addr = await _configured_treasury()
    chain = SolanaLive(SOLANA_RPC, fallbacks=SOLANA_FALLBACKS)
    state = await chain.treasury_state(treasury_addr, mint) if mint else {}
    price = await live_jupiter_price(mint, os.environ.get("JUPITER_API_KEY", "")) if mint else None

    token_value_usd = None
    if price is not None and state.get("token_balance") is not None:
        token_value_usd = state["token_balance"] * price

    # Token movement across stored agent measurements.
    trend: Dict[str, Any] = {"available": False, "reason": "insufficient_measurements"}
    try:
        since = datetime.now(timezone.utc) - timedelta(days=window_days)
        rows = await db.token_measurements.find(
            {"ts": {"$gte": since}}
        ).sort("ts", 1).to_list(2000)
        if len(rows) >= 2:
            first, last = rows[0], rows[-1]

            def delta(field):
                a, b = first.get(field), last.get(field)
                if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    return {
                        "from": a, "to": b, "delta": round(b - a, 10),
                        "pct": round((b - a) / a * 100, 4) if a else None,
                    }
                return None

            trend = {
                "available": True,
                "measurements": len(rows),
                "from": first.get("ts").isoformat() if hasattr(first.get("ts"), "isoformat") else None,
                "to": last.get("ts").isoformat() if hasattr(last.get("ts"), "isoformat") else None,
                "price_usd": delta("price_usd"),
                "holders": delta("holders"),
                "treasury_sol": delta("treasury_sol"),
                "treasury_token_balance": delta("treasury_token_balance"),
                "volume_24h_usd": delta("volume_24h_usd"),
            }
        else:
            trend["measurements"] = len(rows)
    except Exception as e:
        trend = {"available": False, "reason": "error", "detail": str(e)[:160]}

    return {
        "ok": True,
        "window_days": window_days,
        "treasury_performance": perf,
        "treasury_now": {
            "address": treasury_addr,
            "sol": state.get("sol"),
            "token_balance": state.get("token_balance"),
            "token_value_usd": token_value_usd,
            "note": "Holdings are a position. Value moving is not income.",
        },
        "booked_revenue": {
            **booked,
            "note": (
                "Reconciled payment-processor income only. Stays at zero until a "
                "verified webhook books a real sale; a rising token price is not "
                "revenue."
            ),
        },
        "token_trend": trend,
        "fetched_at": utcnow(),
    }


@api_router.get("/performance")
async def get_performance(window_days: int = Query(30, ge=1, le=365),
                          user: dict = Depends(require_director)):
    """Realised treasury performance measured from recorded snapshots.

    Returns `available: false` with a reason when there is not enough history. It
    never projects, and it never substitutes a formula for a measurement.
    """
    return await treasury_performance(db, window_days=window_days)


async def record_live_snapshot() -> Dict[str, Any]:
    """Read mainnet once and persist a real price + treasury observation.

    These rows are what /api/performance later measures, so nothing is written
    unless the read actually succeeded.
    """
    mint = await _configured_mint()
    treasury_addr = await _configured_treasury()
    chain = SolanaLive(SOLANA_RPC, fallbacks=SOLANA_FALLBACKS)
    written = {"price": False, "treasury": False}
    now = datetime.now(timezone.utc)

    # Field names, timestamp type and retention deliberately match the manual
    # /api/price-snapshot and /api/treasury-snapshot writers, so both producers
    # populate one consistent collection.
    if mint:
        price = await live_jupiter_price(mint, os.environ.get("JUPITER_API_KEY", ""))
        if price is not None:
            await db.price_history.insert_one(
                {"mint": mint, "price": price, "ts": now, "source": "jupiter:v3"}
            )
            await _prune_collection(db.price_history, {"mint": mint})
            written["price"] = True

    # Read SOL and token holdings together. Recording SOL alone made a swap from
    # SOL into the project's own token look like a total loss of that SOL, because
    # performance had no idea the tokens had arrived.
    state = await chain.treasury_state(treasury_addr, mint) if mint else {}
    sol = state.get("sol") if mint else await chain.sol_balance(treasury_addr)
    if sol is not None:
        token_balance = state.get("token_balance")
        token_price_usd = await live_jupiter_price(
            mint, os.environ.get("JUPITER_API_KEY", "")
        ) if mint else None
        sol_price_usd = await live_jupiter_price(
            SOL_MINT, os.environ.get("JUPITER_API_KEY", "")
        )

        token_value_usd = (
            token_balance * token_price_usd
            if token_balance is not None and token_price_usd is not None else None
        )
        # Express the token holding in SOL so performance can add the two sides
        # without mixing units.
        token_value_sol = (
            token_value_usd / sol_price_usd
            if token_value_usd is not None and sol_price_usd else None
        )

        await db.treasury_snapshots.insert_one(
            {
                "address": treasury_addr,
                "balance_sol": sol,
                "balance_usd": sol * sol_price_usd if sol_price_usd else None,
                "token_balance": token_balance,
                "token_value_usd": token_value_usd,
                "token_value_sol": token_value_sol,
                "ts": now,
                "source": "rpc:getBalance+getTokenAccountsByOwner",
            }
        )
        await _prune_collection(db.treasury_snapshots, {})
        written["treasury"] = True

    return written


async def _prune_collection(collection, query: Dict[str, Any], keep: int = 500):
    """Keep the newest `keep` rows, matching the retention the manual writers use."""
    count = await collection.count_documents(query)
    if count <= keep:
        return
    oldest = await collection.find(query).sort("ts", 1).limit(count - keep).to_list(count - keep)
    if oldest:
        await collection.delete_many({"_id": {"$in": [d["_id"] for d in oldest]}})


@api_router.post("/snapshot/now")
async def snapshot_now(user: dict = Depends(require_director)):
    """Force an immediate live observation instead of waiting for the poller."""
    return {"ok": True, "written": await record_live_snapshot(), "at": utcnow()}


async def snapshot_poller(interval_seconds: int = 300):
    """Persist a real observation every interval so performance has history to measure."""
    while True:
        try:
            written = await record_live_snapshot()
            if any(written.values()):
                logger.info(f"📈 Snapshot recorded: {written}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Snapshot poller error: {e}")
        await asyncio.sleep(interval_seconds)


# ── Sweep / Withdrawal Endpoints ────────────────────────────────────────────────

@api_router.post("/sweep")
@limiter.limit("10/minute")
async def log_sweep(request: Request, user: dict = Depends(require_director)):
    """Log a sweep/withdrawal transaction with destination validation."""
    try:
        data = await request.json()
        from_addr = data.get("from", "")
        to_addr = data.get("to", "")
        amount = data.get("amount_sol", 0)
        signature = data.get("signature", "")
        
        # CRITICAL: Treasury can only sweep to authorized destinations
        if from_addr == TREASURY_WALLET:
            validate_withdrawal_destination(to_addr)
        else:
            # Non-treasury sweeps also must go to authorized destinations
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
async def revenue_dashboard(user: dict = Depends(require_director)):
    """Get complete revenue dashboard data."""
    try:
        data = await revenue_system.get_dashboard_data()
        return JSONResponse(content=data)
    except Exception as e:
        logger.error(f"Revenue dashboard error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/revenue/status")
async def revenue_status(user: dict = Depends(require_director)):
    """Get revenue system status. Was marked public; it exposes income and gate
    state, which is operational, so it is now director-only."""
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
async def revenue_check_compliance(request: Request, user: dict = Depends(require_director)):
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
async def _verified_webhook_body(request: Request, source: str) -> Dict[str, Any]:
    """Read and verify a webhook body, or reject it.

    These endpoints book REAL income into the truth ledger, and real_income() is
    what the withdraw phase reads to decide whether to propose a payout. Left
    open, anyone who guessed the URL could inflate it. Director auth is the wrong
    control here because a payment processor cannot hold a hub session, so this
    uses an HMAC over the raw body instead. Fails closed.
    """
    raw = await request.body()
    ok, reason = wh_verify(
        source,
        raw,
        request.headers.get("x-signature") or request.headers.get("x-hub-signature-256"),
        request.headers.get("x-timestamp"),
    )
    if not ok:
        logger.warning(f"rejected {source} webhook: {reason}")
        raise HTTPException(status_code=401, detail=f"webhook rejected: {reason}")
    try:
        return json.loads(raw or b"{}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid JSON body: {e}")


@api_router.get("/revenue/webhooks/status")
async def revenue_webhook_status(user: dict = Depends(require_director)):
    """Which webhook sources have a secret configured. Secrets are never returned."""
    return {
        "ok": True,
        "sources": wh_configured_sources(),
        "note": (
            "Webhooks fail closed. Without a secret, income cannot be booked from "
            "any source. Set WEBHOOK_SECRET, or WEBHOOK_SECRET_<SOURCE> per source."
        ),
    }


@api_router.post("/revenue/webhooks/product-sale")
@limiter.limit("60/minute")
async def revenue_webhook_product_sale(request: Request):
    """Product sale webhook (Stripe, Gumroad, etc.). Signature required."""
    data = await _verified_webhook_body(request, "product")
    try:
        result = revenue_system.handle_product_sale(data)

        if result.get("ok"):
            # Durable first: an in-memory ledger loses this on the next restart,
            # and Render's free tier sleeps after ~15 minutes idle.
            await ledger_persist(db, revenue_system.ledger._entries[-1])
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
@limiter.limit("60/minute")
async def revenue_webhook_invoice_paid(request: Request):
    """Invoice paid webhook (for agency services). Signature required."""
    data = await _verified_webhook_body(request, "invoice")
    try:
        result = revenue_system.handle_invoice_paid(data)

        if result.get("ok"):
            await ledger_persist(db, revenue_system.ledger._entries[-1])
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
async def revenue_live_status(user: dict = Depends(require_director)):
    """Get live tracking status."""
    try:
        status = await live_tracker.get_live_status()
        return JSONResponse(content=status)
    except Exception as e:
        logger.error(f"Revenue live status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/revenue/live/dashboard")
async def revenue_live_dashboard(user: dict = Depends(require_director)):
    """Get complete live dashboard with real-time data."""
    try:
        dashboard = await live_tracker.get_live_dashboard()
        return JSONResponse(content=dashboard)
    except Exception as e:
        logger.error(f"Revenue live dashboard error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/revenue/live/metrics")
async def revenue_live_metrics(limit: int = 50,
                               user: dict = Depends(require_director)):
    """Get live metrics stream."""
    try:
        metrics = await live_tracker.get_live_metrics(limit)
        return JSONResponse(content={"metrics": metrics, "count": len(metrics)})
    except Exception as e:
        logger.error(f"Revenue live metrics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/revenue/live/income")
async def revenue_live_income(limit: int = 100,
                              user: dict = Depends(require_director)):
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
async def agents_status(user: dict = Depends(require_director)):
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
# ACHIEVEMENTS - Learning & Milestones from Background Loops
# ─────────────────────────────────────────────────────────────────────────────

@api_router.get("/achievements")
async def get_achievements(
    limit: int = Query(50, le=200),
    category: Optional[str] = Query(None),
    user: dict = Depends(require_director)
):
    """Get recent achievements from background loops and agents."""
    try:
        achievements = await achievement_tracker.get_recent(limit=limit, category=category)
        return {
            "ok": True,
            "achievements": achievements,
            "count": len(achievements)
        }
    except Exception as e:
        logger.error(f"Achievements fetch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/achievements/summary")
async def get_achievements_summary():
    """Get achievement statistics and summary."""
    try:
        summary = await achievement_tracker.get_summary()
        return {
            "ok": True,
            **summary
        }
    except Exception as e:
        logger.error(f"Achievements summary error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/achievements/agent/{agent_id}")
async def get_agent_achievements(agent_id: str, limit: int = Query(20, le=100)):
    """Get achievements for a specific agent."""
    try:
        achievements = await achievement_tracker.get_by_agent(agent_id, limit=limit)
        return {
            "ok": True,
            "agent_id": agent_id,
            "achievements": achievements,
            "count": len(achievements)
        }
    except Exception as e:
        logger.error(f"Agent achievements error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────────────────────────────────────
# Health / API Monitoring

async def check_mongodb_health() -> dict:
    """Check MongoDB connection health."""
    try:
        start = time.time()
        await db_mongo.list_collection_names()
        latency_ms = int((time.time() - start) * 1000)
        return {
            "id": "mongodb",
            "name": "MongoDB",
            "category": "Database",
            "status": "live",
            "latency": latency_ms,
            "url": "Internal MongoDB"
        }
    except Exception as e:
        return {
            "id": "mongodb",
            "name": "MongoDB",
            "category": "Database",
            "status": "error",
            "latency": 0,
            "error": str(e),
            "url": "Internal MongoDB"
        }

async def check_solana_rpc_health() -> dict:
    """Check Solana RPC connection health."""
    try:
        start = time.time()
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                SOLANA_RPC,
                json={"jsonrpc": "2.0", "id": 1, "method": "getHealth"}
            )
        latency_ms = int((time.time() - start) * 1000)
        return {
            "id": "sol-rpc",
            "name": "Solana RPC",
            "category": "Chain",
            "status": "live" if resp.status_code == 200 else "error",
            "latency": latency_ms,
            "url": SOLANA_RPC
        }
    except Exception as e:
        return {
            "id": "sol-rpc",
            "name": "Solana RPC",
            "category": "Chain",
            "status": "error",
            "latency": 0,
            "error": str(e),
            "url": SOLANA_RPC
        }

async def check_jupiter_health() -> dict:
    """Check Jupiter API health."""
    try:
        jupiter_api_key = os.environ.get("JUPITER_API_KEY", "")
        headers = {}
        if jupiter_api_key:
            headers["x-api-key"] = jupiter_api_key
            
        start = time.time()
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Test with SOL price lookup
            resp = await client.get("https://api.jup.ag/price/v3?ids=So11111111111111111111111111111111111111112", headers=headers)
        latency_ms = int((time.time() - start) * 1000)
        return {
            "id": "jup",
            "name": "Jupiter Price API",
            "category": "DEX",
            "status": "live" if resp.status_code == 200 else "error",
            "latency": latency_ms,
            "url": "api.jup.ag/price/v3"
        }
    except Exception as e:
        return {
            "id": "jup",
            "name": "Jupiter Price API",
            "category": "DEX",
            "status": "error",
            "latency": 0,
            "error": str(e),
            "url": "api.jup.ag/price/v3"
        }

async def check_revenue_system_health() -> dict:
    """Check Revenue System health."""
    try:
        start = time.time()
        status_data = revenue_system.ledger.summary()
        latency_ms = int((time.time() - start) * 1000)
        return {
            "id": "revenue",
            "name": "Revenue System",
            "category": "Internal",
            "status": "live",
            "latency": latency_ms,
            "url": f"${status_data.get('real_income', 0):.2f} real income"
        }
    except Exception as e:
        return {
            "id": "revenue",
            "name": "Revenue System",
            "category": "Internal",
            "status": "error",
            "latency": 0,
            "error": str(e),
            "url": "Internal Revenue System"
        }

async def check_agent_pool_health() -> dict:
    """Check Agent Pool health."""
    try:
        start = time.time()
        agent_status = agent_pool.get_status()
        latency_ms = int((time.time() - start) * 1000)
        return {
            "id": "agents",
            "name": "Agent Pool",
            "category": "Internal",
            "status": "live",
            "latency": latency_ms,
            "url": f"{agent_status['total_agents']} agents active"
        }
    except Exception as e:
        return {
            "id": "agents",
            "name": "Agent Pool",
            "category": "Internal",
            "status": "error",
            "latency": 0,
            "error": str(e),
            "url": "Internal Agent Pool"
        }

@api_router.get("/health/details")
@limiter.limit("30/minute")
async def health_details(request: Request, user: dict = Depends(require_director)):
    """Return detailed health metrics for all backend integrations.

    Gated: it names upstream providers and their latencies, which is infrastructure
    reconnaissance rather than anything a holder needs."""
    health_status = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": []
    }
    
    # Run all health checks concurrently for better performance
    checks = await asyncio.gather(
        check_mongodb_health(),
        check_solana_rpc_health(),
        check_jupiter_health(),
        check_revenue_system_health(),
        check_agent_pool_health(),
        return_exceptions=True
    )
    
    # Add all check results to services list
    for check_result in checks:
        if isinstance(check_result, dict):
            health_status["services"].append(check_result)
        else:
            # If a check raised an exception, log it
            logger.error(f"Health check failed: {check_result}")
    
    return JSONResponse(content=health_status)

# ─────────────────────────────────────────────────────────────────────────────

@api_router.get("/")
async def root():
    return {"message": "YABBAI API running", "status": "ok", "version": "2.0"}

app.include_router(api_router)

# CORS. allow_credentials=True means the session cookie can ride on cross-origin
# requests, so the origin list must never be '*' in production — a wildcard with
# credentials lets any site on the internet make authenticated calls on behalf of a
# logged-in Director. Default to the known hosts rather than to '*'.
_DEFAULT_ORIGINS = ",".join([
    "https://yabbai.network",
    "https://command.yabbai.network",
    "https://token.yabbai.network",
    "https://holders.yabbai.network",
])
_cors_origins = [
    o.strip()
    for o in os.environ.get("CORS_ORIGINS", _DEFAULT_ORIGINS).split(",")
    if o.strip()
]
if "*" in _cors_origins:
    logger.error(
        "CORS_ORIGINS contains '*' while credentials are allowed. Refusing the "
        "wildcard and falling back to the known-host list."
    )
    _cors_origins = _DEFAULT_ORIGINS.split(",")

logger.info(f"CORS origins: {_cors_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

@app.on_event("startup")
async def startup_revenue_tracker():
    """Start the live revenue tracking and agent pool on startup."""
    global background_task, agent_pool_task, snapshot_task
    try:
        # Start background orchestrator
        background_task = asyncio.create_task(live_tracker.start_background_orchestrator())
        logger.info("✅ Live Revenue Tracker started")

        # Start multi-agent pool
        agent_pool_task = asyncio.create_task(agent_pool.start())
        logger.info("✅ Multi-Agent Pool started")

        # Persist real mainnet observations so performance has history to measure
        snapshot_task = asyncio.create_task(snapshot_poller(SNAPSHOT_INTERVAL))
        logger.info(f"✅ Snapshot poller started ({SNAPSHOT_INTERVAL}s interval)")

        # Restore the truth ledger. Without this the in-memory ledger starts empty
        # on every boot, so real income booked before the last restart disappears.
        await ledger_ensure_indexes(db)
        stored = await ledger_load_all(db)
        if stored:
            totals = await ledger_totals(db)
            logger.info(
                f"✅ Truth ledger restored: {len(stored)} metric(s), "
                f"real income ${totals.get('real_income')}"
            )
        else:
            logger.info("✅ Truth ledger empty (no revenue recorded yet)")

    except Exception as e:
        logger.error(f"Failed to start systems: {e}")

@app.on_event("shutdown")
async def shutdown_db_client():
    """Shutdown database and stop all systems."""
    global background_task, agent_pool_task, snapshot_task
    try:
        await live_tracker.stop_background_orchestrator()
        if background_task:
            background_task.cancel()
        logger.info("⏸️  Live Revenue Tracker stopped")

        await agent_pool.stop()
        if agent_pool_task:
            agent_pool_task.cancel()
        logger.info("⏸️  Multi-Agent Pool stopped")

        if snapshot_task:
            snapshot_task.cancel()
        logger.info("⏸️  Snapshot poller stopped")

    except Exception as e:
        logger.error(f"Error stopping systems: {e}")
    client.close()
