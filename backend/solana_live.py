#!/usr/bin/env python3
"""
YABBAI — Live Solana mainnet reads.

Every function here returns either a real value read from chain, or None. There are
no defaults, no placeholders, and no estimates. A None means "we could not read this",
and callers must surface that as DATA GAP rather than substituting a number.

Read-only by construction: this module only ever issues RPC read methods. It holds no
keys and can sign nothing.
"""

import asyncio
import base64
import logging
import struct
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

# SPL token account layout: mint(32) | owner(32) | amount(u64 LE)
_AMOUNT_OFFSET = 64
_AMOUNT_LEN = 8
_SPL_ACCOUNT_SIZE = 165

LAMPORTS_PER_SOL = 1_000_000_000


class RpcError(RuntimeError):
    """Raised when the RPC endpoint returns a JSON-RPC error object."""


class SolanaLive:
    """Thin async client over the Solana JSON-RPC. Read methods only."""

    def __init__(
        self,
        rpc_url: str,
        timeout: float = 12.0,
        max_concurrency: int = 3,
        max_retries: int = 3,
    ):
        self.rpc_url = rpc_url
        self.timeout = timeout
        self.max_retries = max_retries
        self._id = 0
        # Callers fan out with asyncio.gather. Providers rate-limit bursts, and a
        # throttled read returns None, which the UI renders as DATA GAP — so an
        # unthrottled burst silently turns real data into "unavailable". Cap the
        # in-flight requests instead of hammering and losing fields.
        self._sem = asyncio.Semaphore(max_concurrency)

    # A provider refusing a method on plan grounds will refuse it forever. Retrying
    # wastes three round trips and delays the DATA GAP the UI needs to show.
    _PERMANENT_MARKERS = (
        "plan upgrade",
        "requires plan",
        "dedicated node",
        "not available on",
        "method not found",
        "unsupported method",
    )

    @classmethod
    def _is_permanent_refusal(cls, body: Optional[dict]) -> bool:
        if not body or not isinstance(body.get("error"), dict):
            return False
        msg = str(body["error"].get("message", "")).lower()
        return any(m in msg for m in cls._PERMANENT_MARKERS)

    @classmethod
    def _is_rate_limited(cls, status: int, body: Optional[dict]) -> bool:
        if cls._is_permanent_refusal(body):
            return False
        if status == 429:
            return True
        if status == 403 and body and isinstance(body.get("error"), dict):
            msg = str(body["error"].get("message", "")).lower()
            return "rate" in msg or "too many" in msg or "throttl" in msg
        return False

    async def _rpc(self, method: str, params: List[Any]) -> Any:
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            async with self._sem:
                try:
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        resp = await client.post(
                            self.rpc_url,
                            json=payload,
                            headers={"Content-Type": "application/json"},
                        )
                except Exception as e:  # transport-level failure
                    last_error = e
                    resp = None

            if resp is not None:
                try:
                    body = resp.json()
                except Exception:
                    body = None

                if self._is_permanent_refusal(body):
                    # Provider will never serve this method on the current plan.
                    raise RpcError(f"{method}: {body['error'].get('message')}")
                if self._is_rate_limited(resp.status_code, body):
                    last_error = RpcError(f"{method}: rate limited ({resp.status_code})")
                elif resp.status_code >= 400:
                    # A genuine method rejection will not succeed on retry.
                    if body and isinstance(body.get("error"), dict):
                        raise RpcError(f"{method}: {body['error']}")
                    resp.raise_for_status()
                elif body is not None:
                    if "error" in body:
                        raise RpcError(f"{method}: {body['error']}")
                    return body.get("result")

            if attempt < self.max_retries - 1:
                # 0.4s, 0.8s, 1.6s — enough for a per-second window to roll over.
                await asyncio.sleep(0.4 * (2 ** attempt))

        raise last_error or RpcError(f"{method}: failed after {self.max_retries} attempts")

    # ── Token facts ────────────────────────────────────────────────────────────

    async def token_supply(self, mint: str) -> Optional[Dict[str, Any]]:
        """Circulating supply straight from the mint account."""
        try:
            result = await self._rpc("getTokenSupply", [mint])
            value = (result or {}).get("value") or {}
            if "uiAmount" not in value:
                return None
            return {
                "supply_raw": value.get("amount"),
                "decimals": value.get("decimals"),
                "supply": value.get("uiAmount"),
                "source": "rpc:getTokenSupply",
            }
        except Exception as e:
            logger.warning(f"token_supply({mint}) failed: {e}")
            return None

    async def mint_authorities(self, mint: str) -> Optional[Dict[str, Any]]:
        """Mint and freeze authority. Null authorities mean the mint is revoked —
        a fact holders care about and one that can be proven from chain."""
        try:
            result = await self._rpc(
                "getAccountInfo", [mint, {"encoding": "jsonParsed"}]
            )
            info = (
                ((result or {}).get("value") or {}).get("data", {}).get("parsed", {})
            ).get("info")
            if not info:
                return None
            return {
                "mint_authority": info.get("mintAuthority"),
                "freeze_authority": info.get("freezeAuthority"),
                "mint_revoked": info.get("mintAuthority") is None,
                "freeze_revoked": info.get("freezeAuthority") is None,
                "source": "rpc:getAccountInfo",
            }
        except Exception as e:
            logger.warning(f"mint_authorities({mint}) failed: {e}")
            return None

    async def largest_accounts(self, mint: str) -> Optional[List[Dict[str, Any]]]:
        """Top token accounts by balance (RPC returns up to 20)."""
        try:
            result = await self._rpc("getTokenLargestAccounts", [mint])
            value = (result or {}).get("value")
            if value is None:
                return None
            return [
                {
                    "address": a.get("address"),
                    "amount": a.get("uiAmount"),
                    "decimals": a.get("decimals"),
                }
                for a in value
            ]
        except Exception as e:
            logger.warning(f"largest_accounts({mint}) failed: {e}")
            return None

    async def holder_count(self, mint: str) -> Optional[Dict[str, Any]]:
        """Count token accounts holding a non-zero balance.

        Uses getProgramAccounts with a dataSlice so only the 8-byte amount field
        crosses the wire instead of every full account. Many public RPC providers
        disable getProgramAccounts entirely; when that happens this returns None and
        the caller shows DATA GAP. It does not guess.
        """
        for program_id, use_size_filter in (
            (TOKEN_PROGRAM, True),
            (TOKEN_2022_PROGRAM, False),
        ):
            filters: List[Dict[str, Any]] = [{"memcmp": {"offset": 0, "bytes": mint}}]
            if use_size_filter:
                # Token-2022 accounts vary in size because of extensions, so the
                # dataSize filter is only valid for the classic token program.
                filters.insert(0, {"dataSize": _SPL_ACCOUNT_SIZE})

            try:
                result = await self._rpc(
                    "getProgramAccounts",
                    [
                        program_id,
                        {
                            "encoding": "base64",
                            "dataSlice": {
                                "offset": _AMOUNT_OFFSET,
                                "length": _AMOUNT_LEN,
                            },
                            "filters": filters,
                        },
                    ],
                )
            except Exception as e:
                logger.warning(f"holder_count({mint}) via {program_id[:8]} failed: {e}")
                continue

            if not result:
                continue

            holders = 0
            for account in result:
                try:
                    raw = account["account"]["data"][0]
                    amount = struct.unpack("<Q", base64.b64decode(raw))[0]
                    if amount > 0:
                        holders += 1
                except Exception:
                    continue

            return {
                "holders": holders,
                "token_accounts": len(result),
                "program": program_id,
                "source": "rpc:getProgramAccounts",
            }

        return None

    # ── Wallet facts ───────────────────────────────────────────────────────────

    async def sol_balance(self, owner: str) -> Optional[float]:
        try:
            result = await self._rpc("getBalance", [owner])
            lamports = (result or {}).get("value")
            if lamports is None:
                return None
            return lamports / LAMPORTS_PER_SOL
        except Exception as e:
            logger.warning(f"sol_balance({owner}) failed: {e}")
            return None

    async def token_holdings(self, owner: str) -> Optional[List[Dict[str, Any]]]:
        """Every SPL token balance held by an owner, across both token programs."""
        holdings: List[Dict[str, Any]] = []
        any_success = False

        for program_id in (TOKEN_PROGRAM, TOKEN_2022_PROGRAM):
            try:
                result = await self._rpc(
                    "getTokenAccountsByOwner",
                    [owner, {"programId": program_id}, {"encoding": "jsonParsed"}],
                )
            except Exception as e:
                logger.warning(f"token_holdings({owner}) via {program_id[:8]}: {e}")
                continue

            any_success = True
            for account in (result or {}).get("value", []):
                info = (
                    account.get("account", {})
                    .get("data", {})
                    .get("parsed", {})
                    .get("info", {})
                )
                amount = info.get("tokenAmount", {})
                if info.get("mint") and amount.get("uiAmount") is not None:
                    holdings.append(
                        {
                            "mint": info["mint"],
                            "amount": amount["uiAmount"],
                            "decimals": amount.get("decimals"),
                        }
                    )

        return holdings if any_success else None

    async def treasury_state(
        self, owner: str, mint: Optional[str] = None
    ) -> Dict[str, Any]:
        """Full read of a treasury wallet. Fields are None where the read failed."""
        sol, holdings = await asyncio.gather(
            self.sol_balance(owner), self.token_holdings(owner)
        )

        token_balance = None
        if mint and holdings is not None:
            token_balance = sum(h["amount"] for h in holdings if h["mint"] == mint)

        return {
            "owner": owner,
            "sol": sol,
            "token_balance": token_balance,
            "holdings": holdings,
            "source": "rpc:mainnet",
        }


async def jupiter_price(mint: str, api_key: str = "", timeout: float = 8.0) -> Optional[float]:
    """Spot USD price from Jupiter. None when unavailable — never zero."""
    headers = {"Accept": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                "https://api.jup.ag/price/v3", params={"ids": mint}, headers=headers
            )
        if resp.status_code != 200:
            logger.warning(f"jupiter_price({mint}) HTTP {resp.status_code}")
            return None
        entry = resp.json().get(mint) or {}
        price = entry.get("usdPrice", entry.get("price"))
        return float(price) if price is not None else None
    except Exception as e:
        logger.warning(f"jupiter_price({mint}) failed: {e}")
        return None
