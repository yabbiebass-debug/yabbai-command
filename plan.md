# plan.md — YABBAI (FARM stack) — Scale-up Roadmap (Updated)

## 1) Objectives
- ✅ Port the provided reference UI/UX to FARM: **FastAPI + React + MongoDB**.
- ✅ Deliver **11 core routes** with the same simulated “live” feel (interval ticks, waveforms, event streams) and dual themes (**YABBAI** vs **BASHAM**).
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
- ⏭️ Finish **frontend wiring + hardening**:
  - Wire `/settings` + `/analytics` routes and navigation
  - Wrap app with `ToastProvider`
  - Upgrade **Command Centre** and **Token App** to load live stats/config from backend
  - Add **429 rate limit** handling (toasts + retry guidance)
  - Run full E2E regression tests for Phase 3+4

**Current status**
- App is live: https://yabbai-command.preview.emergentagent.com
- ✅ Phase 1 + Phase 2 completed (MVP fully tested).
- ✅ Withdraw + Wallet updated for **sweep/recovery** flows.
- ✅ Backend has been upgraded for Phase 3+4:
  - MongoDB endpoints added for `settings`, `missions`, `transactions`, `treasury snapshots`, `price history`, and `sweep` logging.
  - SlowAPI rate limiting + in-memory caching scaffolding exists.
- ✅ Frontend Phase 3+4 files created:
  - `ToastContext.js`, `CopyButton.js`, `Skeleton.js`
  - New pages: `Settings.js`, `Analytics.js`
  - `Mission.js` and `Promo.js` upgraded to use backend APIs
- 🚧 Remaining: new pages are not yet routed; `CommandCentre.js` + `YabbaiApp.js` still rely primarily on simulated state; rate-limit (429) UX not yet standardized.

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
- ✅ Withdraw tab refactored into **Treasury Sweep / Fund Recovery** flow:
  - live connected-wallet balance via backend RPC
  - % presets + MAX SAFE (fee buffer)
  - sweep confirmation state + session history
- ✅ Wallet tab includes **Quick Sweep** widget (destination + % presets + on-chain send).

**Phase 2 testing (end-to-end)**
- ✅ Full navigation and key interactions validated across all pages.
- ✅ Backend endpoints validated including input validation and graceful error handling.

---

### Phase 3 — Hardening + Production polish (IN PROGRESS)
Goal: reduce warnings, improve resilience/performance, and tighten UX edge cases while preparing for DB-backed features.

**Engineering hardening**
- ✅ Added global toast notification system (`ToastContext.js`) (not yet wired into router).
- ✅ Added UI utilities: `CopyButton`, `Skeleton`.
- [ ] Wire `ToastProvider` into `App.js` so all pages can show consistent error UX.
- [ ] Introduce standardized API error handling via a small `apiClient` wrapper (recommended) or consistent inline fetch handling.
- [ ] Prioritize error UX **now**:
  - show toasts for 429 Too Many Requests (rate limiting)
  - show toasts for network failures/timeouts
  - suggest retry after short delay or switch RPC if configured

**Performance**
- [ ] Re-audit all `setInterval` and RAF loops; ensure teardown on unmount.
- [ ] Pause/reduce animation work on hidden tab (`document.visibilityState`).

**Security / MVP hygiene**
- ✅ Strengthened server-side validation patterns (base58 helper present; ensure used consistently).
- ✅ SlowAPI rate limiting added to backend.
- [ ] Make CORS origin list environment-driven for production.

**UX polish**
- ✅ CopyButton utility component (mint, treasury, addresses, tx sigs).
- ✅ Skeleton/loading components exist.
- [ ] Apply skeletons + toasts to key fetches (wallet balance, sweeps, analytics loads).

**Phase 3 testing**
- [ ] Re-run E2E regression across all routes after wiring.
- [ ] Add targeted tests for sweep UX edge cases (MAX SAFE, invalid destination, insufficient funds, 429 handling).

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
- ✅ SlowAPI limits enabled (verify per-endpoint configuration during testing).
- ✅ In-memory caching (TTL) implemented for hot endpoints:
  - price cache per mint (TTL ~30s)
  - balance cache per owner (TTL ~15s)

#### 4.3 Frontend: New pages ✅ CREATED (wiring pending)
- ✅ **`/settings`** page created:
  - configure treasury/main wallet, fee buffer, slippage, AI defaults, demo mode
- ✅ **`/analytics`** page created (Recharts):
  - treasury balance chart
  - transaction volume chart
  - mission status chart
  - transaction table

#### 4.4 Frontend: Upgrades to existing pages (IN PROGRESS)
- ✅ **Mission Builder** updated to use backend APIs.
- ✅ **Promo** updated to use backend APIs.
- [ ] **Command Centre (/)**: replace simulated headline stats with backend-driven telemetry where available:
  - treasury snapshots + latest treasury SOL
  - mission counts
  - transaction counts
  - optionally price history latest price
- [ ] **YabbaiApp (/yabbai)**:
  - load/save token configuration via backend
  - optionally poll backend price and trigger snapshot writes when configured
- [ ] **Withdraw + Wallet**:
  - ensure sweep actions POST `/api/sweep` and also record in `/api/transactions` (if not already)
  - surface persisted transaction history (not only session)

#### 4.5 Shared UX utilities (IN PROGRESS)
- ✅ Toast system implemented.
- ✅ CopyButton implemented.
- ✅ Skeleton components implemented.
- [ ] Add a shared `apiClient` wrapper to normalize errors and prioritize **429** handling across the app:
  - detect `res.status === 429`
  - toast a clear “Rate limited—try again shortly” message
  - optionally read `Retry-After` header if present

**Phase 4 testing**
- [ ] API validation checks (manual + automated): settings save/load, missions CRUD, sweep logging, analytics summary.
- [ ] Frontend E2E: settings save, analytics rendering, mission persistence, sweep persistence.

---

## 3) Next Actions
**P0 — Wire the new Phase 3+4 frontend (immediate)**
1. Update `App.js`:
   - wrap app with `<ToastProvider>`
   - add routes: `/settings`, `/analytics`
2. Update `Layout.js`:
   - add nav links for Settings + Analytics

**P0 — Error UX + rate limit handling (prioritized now)**
3. Implement standardized fetch handling:
   - toast on non-OK responses
   - special-case 429 with a clear retry message

**P0 — Backend integration for core pages**
4. Upgrade `CommandCentre.js` to fetch live stats from backend endpoints.
5. Upgrade `YabbaiApp.js` to fetch/save settings/mint config from backend endpoints.

**P0 — Testing**
6. Run comprehensive E2E regression (`testing_agent_v3`) after wiring is complete.
7. Fix any regressions (routing, missing env vars, API shape mismatches, chart rendering errors).

**P1 — Additional hardening**
8. Add error boundary.
9. Reduce animation load on hidden tabs.
10. Make CORS origin list environment-driven.

---

## 4) Success Criteria
- ✅ All current routes render with correct theme + animations.
- ✅ Sweep/Fund recovery works: connected wallet → destination → presets/MAX SAFE → confirmed tx.
- Phase 3 complete when:
  - no critical console errors
  - hook warnings addressed
  - global toasts integrated (ToastProvider wired)
  - 429 rate limiting errors are displayed clearly and consistently
- Phase 4 complete when:
  - settings, missions, transactions persist to MongoDB
  - sweeps are stored and displayed as history
  - price + treasury snapshots populate analytics
  - `/settings` and `/analytics` are fully accessible via routes + nav
  - Command Centre + Token App are backend-driven where applicable
  - E2E regression passes for Phase 3+4
