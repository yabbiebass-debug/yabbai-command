"""
YABBAI COMMAND — hub SSO gate (spoke side). Apply VERBATIM.

command.yabbai.network does NOT run its own login, signup, or credential store.
yabbai.network is the identity provider (Emergent Google sign-in + email
allowlist + Google Authenticator TOTP). The shared session cookie
(Domain=.yabbai.network, minted only by the hub) is verified here by calling the
hub's /api/auth/sso/verify — which returns 200 ONLY for a fully verified
Director. No secrets are shared between the two apps. Fails closed on any doubt.

Env (backend/.env AND the deployment secrets panel):
  HUB_AUTH_URL=https://yabbai.network    # unset => every request 503s (fail closed)

Mount in server.py:
  from hub_sso import router as sso_router, require_director
  app.include_router(sso_router)
Protect any sensitive route:
  @app.get("/api/whatever")
  async def whatever(user: dict = Depends(require_director)): ...
"""
import os
from typing import Optional

import httpx
from fastapi import APIRouter, Request, Response, HTTPException, Header

COOKIE_NAME = "session_token"
COOKIE_DOMAIN = ".yabbai.network"   # parent domain — shared with the hub
HUB_AUTH_URL = (os.environ.get("HUB_AUTH_URL", "") or "").strip().rstrip("/")

router = APIRouter(prefix="/api/auth", tags=["auth-sso"])


def _token(request: Request, authorization: Optional[str]) -> Optional[str]:
    tok = request.cookies.get(COOKIE_NAME)
    if not tok and authorization and authorization.lower().startswith("bearer "):
        tok = authorization[7:].strip()
    return tok


async def require_director(request: Request, authorization: Optional[str] = Header(None)) -> dict:
    """FastAPI dependency: verified Director via the hub. Fail closed on any doubt."""
    if not HUB_AUTH_URL:
        raise HTTPException(503, "SSO not configured (HUB_AUTH_URL unset) — failing closed.")
    tok = _token(request, authorization)
    if not tok:
        raise HTTPException(401, "Not authenticated")
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{HUB_AUTH_URL}/api/auth/sso/verify",
                            headers={"Authorization": f"Bearer {tok}"})
    except Exception:
        raise HTTPException(503, "Hub auth unreachable — failing closed.")
    if r.status_code != 200:
        raise HTTPException(r.status_code if r.status_code in (401, 403) else 401,
                            "Not authorised by hub")
    return r.json()["user"]


@router.get("/me")
async def me(request: Request, authorization: Optional[str] = Header(None)):
    return await require_director(request, authorization)


@router.post("/logout")
async def logout(request: Request, response: Response, authorization: Optional[str] = Header(None)):
    tok = _token(request, authorization)
    if tok and HUB_AUTH_URL:
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                await c.post(f"{HUB_AUTH_URL}/api/auth/logout",
                             headers={"Authorization": f"Bearer {tok}"})
        except Exception:
            pass  # hub session may already be gone; still clear the shared cookie
    response.delete_cookie(COOKIE_NAME, path="/", samesite="none", secure=True,
                           domain=COOKIE_DOMAIN)
    return {"ok": True}
