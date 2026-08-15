# plan.md — YABBAI Command Centre (FARM stack) — Scale-up Roadmap (Updated)

## 1) Objectives
- ✅ Port the provided reference UI/UX to FARM: **FastAPI + React + MongoDB**.
- ✅ Deliver **11 core routes** with the same “live” feel (interval ticks, waveforms, event streams) and dual themes (**YABBAI** vs **BASHAM**).
- ✅ Preserve key visual system: ultra-dark (#060E20), Solana Purple/Green, amber, glass/scanlines/neon, fonts, animations.
- ✅ Ensure deployment-ready app preview is working end-to-end.
- ✅ Add **fund recovery / treasury sweep UX**:
  - Withdraw tab upgraded to “Treasury Sweep” (connect → set destination → % presets/MAX SAFE → sweep)
  - Wallet tab upgraded with “Quick Sweep” widget

**Scale-up objectives (Phase 3+4)**
- ✅ Add persistent, DB-backed platform features (settings, missions, transactions, telemetry):
  - Settings CRUD (site + treasury config)
  - Mission persistence (save/load/delete)
  - Transaction persistence (save sweeps + other ops)
  - Price history + treasury snapshots for analytics
- ✅ Add **rate limiting + caching** foundations to protect/provide fast API proxying (SlowAPI + TTL caches).
- ✅ Add new pages and UX utilities:
  - `/settings` (owner controls / config)
  - `/analytics` (charts + telemetry)
  - Toast notifications (global)
  - CopyButton
  - Skeleton loading components

**NEW governing objective (Data Integrity / Truth Mode)**
- ⚠️ **Partially shipped; audit not complete project-wide.**
  - ✅ Remove/disable mock/simulated/fabricated numeric displays in key pages already touched.
  - ✅ If data is not available, UI must show **Not Connected**, **Configure in Settings**, or **DATA GAP** (never default to `0` when unknown).
  - ✅ Mock data may only remain in explicitly labeled **AI/learning** components; it must be visually and textually labeled as **Learning/Simulation** and must not be mixed into “real” totals.
  - ✅ Any simulation mode must show an explicit disclosure banner.

**NEW governing objective (Hub SSO / Zero-credential spoke)**
- ✅ Command app stores **zero credentials** and does not implement login/signup/password/OAuth.
- ✅ Hub (`https://yabbai.network`) is the sole identity provider.
- ✅ Command backend verifies sessions live against hub via `hub_sso.py` (verbatim).
- ✅ Fail closed:
  - `HUB_AUTH_URL` unset ⇒ **503**
  - Not authenticated ⇒ **401**
- ✅ Import-order fix applied and verified: `load_dotenv()` runs **before** importing `hub_sso`.
- ✅ Director-only protection enforced:
  - ✅ Backend: sensitive routes require `Depends(require_director)`
  - ✅ Frontend: all routes wrapped with `ProtectedRoute`
- ✅ SSO verification/testing completed in preview (within honest limits of cookie scoping).

**Current status**
- Preview app: https://yabbai-command.preview.emergentagent.com
- Production app: https://command.yabbai.network (operator-managed deploy)

**Verified recently (preview / supervised backend)**
- ✅ Fixed Hub SSO import ordering in `/app/backend/server.py` so dotenv loads before `hub_sso` import.
- ✅ `/api/auth/me` returns **401** with no cookie when `HUB_AUTH_URL` is configured (previously incorrect **503**).
- ✅ Frontend compilation passes after wiring `ProtectedRoute` into `App.js`.
- ✅ Testing agent run passed 100% for backend + frontend SSO gating and sensitive route protection (`/app/test_reports/iteration_8.json`).

**Operator actions (production secrets panel)**
- Required in **yabbai-command** deployment secrets panel:
  - `HUB_AUTH_URL=https://yabbai.network`
- Required in **hub** deployment secrets panel (if not already done):
  - `COOKIE_DOMAIN=.yabbai.network`
- No API keys/tokens/credentials are needed for SSO beyond these environment values.

---

## 2) Implementation Steps

### Phase 1 — Core POC (Isolation) ✅ COMPLETE
**Core risk addressed:** external integrations + persistence powering “live mode”: MongoDB CRUD + proxy endpoints (Jupiter + Solana RPC).

**Delivered**
- ✅ FastAPI app connects to MongoDB.
- ✅ Endpoints implemented:
  1. `GET /api/token-mint` returns `{configured:false}` when empty.
  2. `POST /api/token-mint` upserts mint config (with input validation).
  3. `DELETE /api/token-mint` clears record.
  4. `GET /api/jupiter-price?mint=...` returns `{ok:true, price:number|null}` with graceful failure modes.
  5. `GET /api/solana-balance?owner=...` returns `{ok:true, sol:number, tokens:[...]}` with graceful failure modes.

**Exit criteria**
- ✅ Mongo record persists across server restart.
- ✅ Proxy endpoints handle invalid inputs gracefully.
- ✅ Stable JSON shapes verified by tests.

---

### Phase 2 — V1 App Development (Frontend + Backend wiring) ✅ COMPLETE

**Repo structure / wiring**
- ✅ Backend: FastAPI under `/app/backend` with `/api` routes.
- ✅ Frontend: CRA + CRACO React app under `/app/frontend` using React Router DOM.

**Backend (MVP)**
- ✅ Mongo collection: `token_mint_config` with fields: `configured, mint, decimals, supply, treasury, mainWallet, network, launchpad, tx, launchedAt`.
- ✅ Implemented routes:
  - `GET/POST/DELETE /api/token-mint`
  - `GET /api/jupiter-price`
  - `GET /api/solana-balance`

**Frontend (ported pages + design system)**
- ✅ Global CSS in `src/index.css`.
- ✅ Fonts added to `public/index.html`.
- ✅ Shared layout: sticky nav, mobile menu, ticker tape, theme switching.

**Solana client support**
- ✅ CRA/CRACO polyfills and fallbacks for `@solana/web3.js`.

**Pages (11 routes) — all implemented**
1. ✅ `/` Command Centre
2. ✅ `/yabbai` Token App
3. ✅ `/launch` Launch sequence
4. ✅ `/payment` Payment Engine
5. ✅ `/mission` Mission Builder
6. ✅ `/wallet` Wallet
7. ✅ `/withdraw` Withdraw / Sweep portal
8. ✅ `/api-pulse` API Pulse
9. ✅ `/basham` Gold Harvester
10. ✅ `/side-hustle` Side Hustle Protocol
11. ✅ `/promo` Promo generator

**Post-V1 upgrades already applied**
- ✅ Withdraw tab refactored into **Treasury Sweep / Fund Recovery** flow.
- ✅ Wallet tab includes **Quick Sweep** widget.

**Phase 2 testing (end-to-end)**
- ✅ Full navigation and key interactions validated across all pages.
- ✅ Backend endpoints validated including input validation and graceful error handling.

---

### Phase 3 — Hardening + Production polish (IN PROGRESS)
Goal: reduce warnings, improve resilience/performance, and tighten UX edge cases while preparing for production-grade gating.

**Engineering hardening**
- ✅ Added global toast notification system (`ToastContext.js`).
- ✅ Wired `ToastProvider` into `App.js`.
- ✅ Added UI utilities: `CopyButton`, `Skeleton`.
- [ ] Introduce standardized API error handling via a small `apiClient` wrapper (recommended) or consistent inline fetch handling.

**Security / MVP hygiene**
- ✅ SlowAPI rate limiting added to backend.
- [ ] Make CORS origin list environment-driven for production.

**Performance**
- [ ] Re-audit all `setInterval` and RAF loops; ensure teardown on unmount.
- [ ] Pause/reduce animation work on hidden tab (`document.visibilityState`).

**Phase 3 testing**
- [ ] Re-run E2E regression across all routes after any additional wiring.

---

### Phase 4 — Scale-up: Data model + persistence + analytics (IN PROGRESS)
Goal: evolve from a “premium simulated command centre” to a **telemetry-driven, persistent platform**.

#### 4.1 Backend: New collections + CRUD ✅ COMPLETE
Mongo-backed collections and APIs now exist for:
- ✅ **Settings**: `GET/POST /api/settings`
- ✅ **Missions**: `GET/POST/PUT/DELETE /api/missions`
- ✅ **Transactions**: `GET/POST /api/transactions`
- ✅ **Price History**: `GET /api/price-history?mint=...&limit=...`
- ✅ **Treasury Snapshots**: `GET /api/treasury-snapshots?limit=...`
- ✅ **Sweep**: `POST /api/sweep` to log sweep operations
- ✅ **Analytics summary**: `GET /api/analytics` (used by Analytics page)

#### 4.2 Backend: Rate limiting + caching ✅ COMPLETE (Foundations)
- ✅ SlowAPI limits enabled.
- ✅ In-memory caching (TTL) implemented for hot endpoints.

#### 4.3 Frontend: New pages ✅ CREATED
- ✅ **`/settings`** page created
- ✅ **`/analytics`** page created

#### 4.4 Frontend: Upgrades to existing pages (IN PROGRESS)
- ✅ **Mission Builder** updated to use backend APIs.
- ✅ **Promo** updated to use backend APIs.
- ✅ **Command Centre (/)** fetches real backend status (revenue/agents/live tracking).
- ✅ **YabbaiApp (/yabbai)** now real-data-only with SIMULATION MODE disclosure + DATA GAP.
- [ ] **Withdraw + Wallet**:
  - ensure sweep actions POST `/api/sweep` and also record in `/api/transactions`
  - surface persisted transaction history (not only session)

#### 4.5 Shared UX utilities (IN PROGRESS)
- ✅ Toast system implemented and wired.
- ✅ CopyButton implemented.
- ✅ Skeleton components implemented.
- [ ] Add a shared `apiClient` wrapper to normalize errors and prioritize **429** handling.

**Phase 4 testing**
- [ ] API validation checks: settings save/load, missions CRUD, sweep logging, analytics summary.
- [ ] Frontend E2E: settings save, analytics rendering, mission persistence, sweep persistence.

---

### Phase 5 — Truth Mode / Real-Data-Only Conversion (P0 shipped; audit incomplete)
Goal: enforce the user directive: **everything on the site must be real data**; mock data is seized/removed from user-facing metrics.

#### 5.1 Define “Real Data” contract (Truth Mode) ✅ DONE
- ✅ Real numeric displays come from backend APIs + DB persistence, or real integrations.
- ✅ Unknown/unconfigured renders **Not Connected / Configure / DATA GAP**.
- ✅ Learning/simulation is allowed only if segregated and clearly labeled.

#### 5.2 Page-by-page mock removal (frontend) ⚠️ PARTIAL / NOT FULLY AUDITED
- ✅ **YabbaiApp.js**: removed simulation candles and fake price; added SIMULATION MODE banner + DATA GAP; uses real endpoints.
- ✅ **ApiPulse.js**: removed random metrics; now reads `/api/health/details`.
- ✅ **Basham.js**: removed random wealth score; now calculated from user answers.
- ✅ **CommandCentre.js**: randomness remains only for non-metric visuals with explicit comments.
- ⚠️ Additional pages/components still require audit; do not claim full project-wide mock-data removal.

#### 5.3 Backend support for Truth Mode ✅ DONE
- ✅ Added `/api/health/details` for real reachability/latency monitoring.
- ✅ Jupiter price migrated to `/price/v3` parsing (`usdPrice`) (do not expose any API credentials).

#### 5.4 Verification & regression (IN PROGRESS)
- ✅ Frontend compile passes.
- ✅ Some testing-agent runs exist historically, and SSO regression is now verified; Truth Mode still needs broader audit if/when prioritized.

---

### Phase 6 — Hub SSO (Director-only spoke) ✅ COMPLETE
Goal: Command app is a **spoke** relying on **hub live verification**; stores **zero credentials**.

#### 6.1 Patch integration ✅ COMPLETE
- ✅ `backend/hub_sso.py` present and preserved **verbatim**.
- ✅ SSO router mounted in backend and exposes:
  - `/api/auth/me`
  - `/api/auth/logout`
- ✅ `frontend/src/components/ProtectedRoute.js` implemented per patch requirements.
- ✅ `frontend/public/shared/sso-gate.js` present (static-page reference; SPA uses ProtectedRoute).

#### 6.2 Environment config ✅ COMPLETE (preview)
- ✅ `/app/backend/.env` contains `HUB_AUTH_URL="https://yabbai.network"`.
- ✅ **Import-order fix applied** so dotenv loads before `hub_sso` import.
- ✅ Supervised backend now returns:
  - `/api/auth/me` (no cookie) ⇒ **401** (expected)

#### 6.3 Backend protection audit ✅ COMPLETE
Requirement: **every sensitive route must include** `user: dict = Depends(require_director)`.
- ✅ Protected sensitive write routes including:
  - token mint POST/DELETE
  - settings GET/POST
  - missions POST/PUT/DELETE
  - transactions POST
  - price snapshot POST
  - treasury snapshot POST
  - events POST
  - sweep POST
  - revenue dashboard GET
  - revenue compliance check POST

> Note: Webhook endpoints remain unauthenticated by Director by design; they must rely on webhook signature verification (future hardening item).

#### 6.4 Frontend protection audit ✅ COMPLETE
- ✅ `ProtectedRoute` is used in `App.js` and wraps all routes.
- ✅ Auth check uses `fetch('/api/auth/me', { credentials: 'include' })`.
- ✅ On failure, redirects to `https://yabbai.network/login/index.html?next=<encoded_current_url>`.
- ✅ No local login UI or credential storage.

#### 6.5 Testing (honest limits) ✅ COMPLETE (preview scope)
- ✅ Preview cannot validate cookie-based browser SSO due to cookie scoping.
- ✅ SSO integration regression verified by testing agent:
  - `/api/auth/me` returns 401 without cookie
  - Sensitive routes return 401 without auth
  - ProtectedRoute redirects to hub login
  - Import-order fix confirmed
  - Report: `/app/test_reports/iteration_8.json`

#### 6.6 Production operator steps (required) ⏳ PENDING
- [ ] In **yabbai-command** deployment secrets panel:
  - `HUB_AUTH_URL=https://yabbai.network`
- [ ] In **hub** deployment secrets panel (if not already set):
  - `COOKIE_DOMAIN=.yabbai.network`
- [ ] Redeploy hub (if cookie-domain change not deployed yet), then redeploy command.
- [ ] Production browser test (deployed domains only):
  - Fresh browser → open `https://command.yabbai.network` → bounce to hub login → Google → Authenticator → return to command.

---

## 3) Next Actions (Updated priorities)

### P0 — Production rollout verification (operator-owned)
1. Operator sets deployment secrets:
   - command: `HUB_AUTH_URL=https://yabbai.network`
   - hub (if needed): `COOKIE_DOMAIN=.yabbai.network`
2. Operator redeploys hub (if cookie-domain change needed) then command.
3. Operator performs the real browser SSO flow test on `https://command.yabbai.network`:
   - bounce → hub login → Google → Authenticator → return to command
4. If any step fails, record which step and the observed behavior for hub-side tracing.

### P1 — Security hardening follow-ups (recommended)
5. Add webhook signature verification for `/api/revenue/webhooks/*` endpoints (do not use Director auth; use provider signatures).
6. Consider applying `require_director` to additional operational endpoints as needed (e.g., any admin/status endpoints that should not be public).

### P1 — Product hardening follow-ups (optional)
7. Add a shared `apiClient` wrapper with strong error handling (429 + network timeouts).
8. Re-run E2E regression across all routes after any hardening changes.

> Per current priority, skip broader site-wide Truth Mode/data audit for now.

---

## 4) Success Criteria (Updated)
- ✅ All current routes render with correct theme + animations.
- ✅ **Hub SSO env/import behavior:**
  - `/api/auth/me` returns **401** with no cookie when configured.
  - `HUB_AUTH_URL` unset returns **503** (fail-closed).
- ✅ **Backend security:** all sensitive routes require `Depends(require_director)`.
- ✅ **Frontend security:** all Director-only pages enforce auth via `ProtectedRoute` and redirect to hub login.
- ✅ **Preview verification complete:** testing-agent regression confirms SSO and gating coverage (iteration_8).
- ⏳ **Production deploy correctness (operator):** with secrets set and redeployed, a fresh browser visits `https://command.yabbai.network` and completes:
  - bounce → hub login → Google → Authenticator → return to command.
