# plan.md — YABBAI (FARM stack) — Scale-up Roadmap (Updated)

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
- ✅ Convert the entire site to **REAL DATA ONLY**.
  - ✅ Remove/disable all mock/simulated/fabricated numeric displays (no `Math.random()`-driven metrics, no fake prices/latency/ROI, no seeded candles).
  - ✅ If data is not available, UI must show **Not Connected**, **Configure in Settings**, or **DATA GAP** (never default to `0` when unknown).
  - ✅ Mock data may only remain in explicitly labeled **AI/learning** components; it must be visually and textually labeled as **Learning/Simulation** and must not be mixed into “real” totals.
  - ✅ Any simulation mode must show an explicit disclosure banner.

**Current status**
- App is live (preview): https://yabbai-command.preview.emergentagent.com
- ✅ Phase 1 + Phase 2 completed (MVP fully tested).
- ✅ Withdraw + Wallet updated for **sweep/recovery** flows.
- ✅ Backend upgraded for Phase 3+4:
  - MongoDB endpoints added for `settings`, `missions`, `transactions`, `treasury snapshots`, `price history`, and `sweep` logging.
  - SlowAPI rate limiting + in-memory caching scaffolding exists.
- ✅ Frontend Phase 3+4 files created:
  - `ToastContext.js`, `CopyButton.js`, `Skeleton.js`
  - New pages: `Settings.js`, `Analytics.js`
  - `Mission.js` and `Promo.js` upgraded to use backend APIs
- ✅ CommandCentre fetches backend data (`/api/revenue/status`, `/api/agents/status`, `/api/revenue/live/status`) for headline stats.
- ✅ Payment.js is real-data-only (Truth Protocol enforced; reconciled totals only).

**Truth Mode conversion — COMPLETE**
- ✅ `YabbaiApp.js`: removed seeded candles / simulated price; added SIMULATION MODE banner and DATA GAP states when unconfigured; uses `/api/price-history` + `/api/jupiter-price` when configured.
- ✅ `ApiPulse.js`: removed random status/latency/calls; uses real backend health endpoint.
- ✅ Backend: added `/api/health/details` endpoint measuring MongoDB, Solana RPC, Jupiter reachability, Revenue System, and Agent Pool status.
- ✅ `Basham.js`: removed random wealth scoring; score is calculated from the user’s answers (real input-based).
- ✅ `CommandCentre.js`: already real data; randomness remains only in clearly documented visual-only animations.
- ✅ `Launch.js` + `Mission.js`: randomness retained only as UX pacing for console/typewriter effects (documented).
- ✅ Frontend compiles successfully (esbuild).
- ✅ Screenshots captured to confirm Truth Mode display.
- 🧪 Comprehensive E2E testing agent invoked to validate across routes.

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
Goal: reduce warnings, improve resilience/performance, and tighten UX edge cases while preparing for DB-backed features.

**Engineering hardening**
- ✅ Added global toast notification system (`ToastContext.js`) (not yet wired into router).
- ✅ Added UI utilities: `CopyButton`, `Skeleton`.
- [ ] Wire `ToastProvider` into `App.js` so all pages can show consistent error UX.
- [ ] Introduce standardized API error handling via a small `apiClient` wrapper (recommended) or consistent inline fetch handling.
- [ ] Prioritize error UX:
  - show toasts for 429 Too Many Requests (rate limiting)
  - show toasts for network failures/timeouts
  - suggest retry after short delay or switch RPC if configured

**Performance**
- [ ] Re-audit all `setInterval` and RAF loops; ensure teardown on unmount.
- [ ] Pause/reduce animation work on hidden tab (`document.visibilityState`).

**Security / MVP hygiene**
- ✅ Strengthened server-side validation patterns.
- ✅ SlowAPI rate limiting added to backend.
- [ ] Make CORS origin list environment-driven for production.

**UX polish**
- ✅ CopyButton utility component.
- ✅ Skeleton/loading components exist.
- [ ] Apply skeletons + toasts to key fetches (wallet balance, sweeps, analytics loads).

**Phase 3 testing**
- [ ] Re-run E2E regression across all routes after wiring.
- [ ] Add targeted tests for sweep UX edge cases.

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

#### 4.3 Frontend: New pages ✅ CREATED (wiring pending)
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
- ✅ Toast system implemented.
- ✅ CopyButton implemented.
- ✅ Skeleton components implemented.
- [ ] Add a shared `apiClient` wrapper to normalize errors and prioritize **429** handling.

**Phase 4 testing**
- [ ] API validation checks: settings save/load, missions CRUD, sweep logging, analytics summary.
- [ ] Frontend E2E: settings save, analytics rendering, mission persistence, sweep persistence.

---

### Phase 5 — Truth Mode / Real-Data-Only Conversion ✅ COMPLETE (P0 shipped)
Goal: enforce the user directive: **everything on the site must be real data**; mock data is seized/removed from user-facing metrics.

#### 5.1 Define “Real Data” contract (Truth Mode) ✅ DONE
- ✅ Real numeric displays come from backend APIs + DB persistence, or real integrations.
- ✅ Unknown/unconfigured renders **Not Connected / Configure / DATA GAP**.
- ✅ Learning/simulation is allowed only if segregated and clearly labeled.

#### 5.2 Page-by-page mock removal (frontend) ✅ DONE
- ✅ **YabbaiApp.js**: removed simulation candles and fake price; added SIMULATION MODE banner + DATA GAP; uses real endpoints.
- ✅ **ApiPulse.js**: removed random metrics; now reads `/api/health/details`.
- ✅ **Basham.js**: removed random wealth score; now calculated from user answers.
- ✅ **CommandCentre.js**: metrics are real; randomness exists only for non-metric visuals with explicit comments.
- ✅ **Launch.js / Mission.js**: randomness retained only for UX pacing; documented.

#### 5.3 Backend support for Truth Mode ✅ DONE
- ✅ Added `/api/health/details` for real reachability/latency monitoring.
- ✅ Truth Protocol verified: only `payment_processor` source counts as real income.

#### 5.4 Verification & regression (IN PROGRESS)
- ✅ Grep-based audit performed for `Math.random` usage; removed from metric displays.
- ✅ Frontend compile passes.
- 🧪 Testing agent invoked for comprehensive E2E validation.

---

## 3) Next Actions (Updated priorities)

**P0 — Finish Truth Mode validation**
1. Review testing agent output and fix any regressions.
2. Add a lightweight CI-style “Truth Audit” script:
   - fail build if `Math.random` is used in non-visual metric contexts
   - flag hard-coded currency values that are not sourced

**P0 — Wire + harden**
3. Wire `ToastProvider` into `App.js`.
4. Add a shared `apiClient` wrapper with strong error handling (429 + network timeouts).

**P1 — Persisted transaction history + sweep logging**
5. Ensure Wallet/Withdraw actions are persisted and displayed (DB-backed history).

**P1 — Additional hardening**
6. Reduce animation load on hidden tabs.
7. Make CORS origin list environment-driven.
8. Optional: refresh Browserslist DB in dev environment.

---

## 4) Success Criteria (Updated)
- ✅ All current routes render with correct theme + animations.
- ✅ Sweep/Fund recovery works: connected wallet → destination → presets/MAX SAFE → confirmed tx.
- ✅ **Truth Mode (Real Data Only)**:
  - ✅ no user-facing fake numbers
  - ✅ no `Math.random()`-driven metrics
  - ✅ token page shows disclosure + DATA GAP when unconfigured
  - ✅ unknowns show **Not Connected / Configure / DATA GAP**
  - ✅ learning/simulation data is clearly labeled and segregated
- Phase 3 complete when:
  - no critical console errors
  - global toasts integrated
  - 429 rate limiting errors displayed clearly and consistently
- Phase 4 complete when:
  - settings, missions, transactions persist to MongoDB
  - sweeps stored and displayed as history
  - price + treasury snapshots populate analytics (from real sources only)
  - `/settings` and `/analytics` accessible via routes + nav
  - Command Centre + Token App backend-driven where applicable
  - E2E regression passes
