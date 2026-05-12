from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import httpx
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime, timezone

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

# ── Models ───────────────────────────────────────────────────────────────────

class TokenMintConfig(BaseModel):
    configured: bool = False
    mint: Optional[str] = None
    decimals: Optional[int] = 6
    supply: Optional[str] = "1000000000"
    treasury: Optional[str] = None
    mainWallet: Optional[str] = None
    network: Optional[str] = "mainnet-beta"
    launchpad: Optional[str] = None
    tx: Optional[str] = None
    launchedAt: Optional[str] = None

class TokenMintUpdate(BaseModel):
    mint: str
    decimals: Optional[int] = 6
    supply: Optional[str] = "1000000000"
    treasury: Optional[str] = None
    mainWallet: Optional[str] = None
    network: Optional[str] = "mainnet-beta"
    launchpad: Optional[str] = None
    tx: Optional[str] = None

# ── Token Mint CRUD ──────────────────────────────────────────────────────────

@api_router.get("/token-mint")
async def get_token_mint():
    try:
        record = await db.token_mint_config.find_one({}, {"_id": 0})
        if not record:
            return {"configured": False}
        return record
    except Exception as e:
        logger.error(f"Error fetching token mint: {e}")
        return {"configured": False}

@api_router.post("/token-mint")
async def save_token_mint(body: TokenMintUpdate):
    try:
        import re
        if not re.match(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$', body.mint):
            raise HTTPException(status_code=400, detail="Invalid mint address format")
        
        doc = {
            "configured": True,
            "mint": body.mint,
            "decimals": body.decimals,
            "supply": body.supply,
            "treasury": body.treasury or "7dzgCA8G55VytZ8PS1b99rbbctzCgJbnEoBEYBnn15YR",
            "mainWallet": body.mainWallet or "7dzgCA8G55VytZ8PS1b99rbbctzCgJbnEoBEYBnn15YR",
            "network": body.network or "mainnet-beta",
            "launchpad": body.launchpad,
            "tx": body.tx,
            "launchedAt": datetime.now(timezone.utc).isoformat(),
        }
        await db.token_mint_config.replace_one({}, doc, upsert=True)
        return doc
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving token mint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.delete("/token-mint")
async def delete_token_mint():
    try:
        await db.token_mint_config.delete_many({})
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error deleting token mint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ── Jupiter Price Proxy ──────────────────────────────────────────────────────

@api_router.get("/jupiter-price")
async def get_jupiter_price(mint: str):
    try:
        if not mint or len(mint) < 32:
            return {"ok": False, "price": None, "error": "Invalid mint address"}
        
        async with httpx.AsyncClient(timeout=8.0) as client_h:
            resp = await client_h.get(
                f"https://api.jup.ag/price/v2",
                params={"ids": mint},
                headers={"Accept": "application/json"}
            )
            if resp.status_code == 200:
                data = resp.json()
                price_data = data.get("data", {}).get(mint, {})
                price = price_data.get("price")
                if price is not None:
                    return {"ok": True, "price": float(price), "mint": mint}
                return {"ok": True, "price": None, "mint": mint}
            return {"ok": False, "price": None, "error": f"Jupiter returned {resp.status_code}"}
    except httpx.TimeoutException:
        return {"ok": False, "price": None, "error": "Jupiter API timeout"}
    except Exception as e:
        logger.error(f"Jupiter price error: {e}")
        return {"ok": False, "price": None, "error": str(e)}

# ── Solana Balance Proxy ─────────────────────────────────────────────────────

SOLANA_RPC = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

@api_router.get("/solana-balance")
async def get_solana_balance(owner: str):
    try:
        if not owner or len(owner) < 32:
            return {"ok": False, "error": "Invalid owner address"}
        
        async with httpx.AsyncClient(timeout=10.0) as client_h:
            # Get SOL balance
            sol_resp = await client_h.post(
                SOLANA_RPC,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getBalance",
                    "params": [owner]
                },
                headers={"Content-Type": "application/json"}
            )
            sol_data = sol_resp.json()
            lamports = sol_data.get("result", {}).get("value", 0)
            sol_balance = lamports / 1_000_000_000

            # Get SPL token accounts
            token_resp = await client_h.post(
                SOLANA_RPC,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "getTokenAccountsByOwner",
                    "params": [
                        owner,
                        {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                        {"encoding": "jsonParsed"}
                    ]
                },
                headers={"Content-Type": "application/json"}
            )
            token_data = token_resp.json()
            tokens = []
            accounts = token_data.get("result", {}).get("value", [])
            for account in accounts:
                info = account.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
                mint = info.get("mint")
                amount_raw = info.get("tokenAmount", {}).get("uiAmount", 0)
                decimals = info.get("tokenAmount", {}).get("decimals", 0)
                if mint and amount_raw is not None:
                    tokens.append({"mint": mint, "amount": amount_raw, "decimals": decimals})
            
            return {"ok": True, "sol": sol_balance, "tokens": tokens}
    except httpx.TimeoutException:
        return {"ok": False, "sol": 0, "tokens": [], "error": "RPC timeout"}
    except Exception as e:
        logger.error(f"Solana balance error: {e}")
        return {"ok": False, "sol": 0, "tokens": [], "error": str(e)}

# ── Health ───────────────────────────────────────────────────────────────────

@api_router.get("/")
async def root():
    return {"message": "YABBAI API running", "status": "ok"}

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
