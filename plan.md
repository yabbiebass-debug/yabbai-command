# plan.md — YABBAI (FARM stack port)

## 1) Objectives
- ✅ Port the provided reference UI/UX to FARM: **FastAPI + React + MongoDB**.
- ✅ Deliver **11 routes** with the same simulated “live” feel (interval ticks, waveforms, event streams) and dual themes (**YABBAI** vs **BASHAM**).
- ✅ Implement backend APIs:
  - `token-mint` (CRUD, persisted in MongoDB)
  - `jupiter-price` (proxy price lookup)
  - `solana-balance` (proxy on-chain balances)
- ✅ Preserve key visual system: ultra-dark (#060E20), Solana Purple/Green, amber, glass/scanlines/neon, fonts, animations.
- ✅ Ensure deployment-ready app preview is working end-to-end.

**Current status**
- App is live: https://yabbai-command.preview.emergentagent.com
- Phase 1 + Phase 2 completed.
- E2E testing completed with **100% pass rate** (backend + frontend).

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
- ✅ Environment options supported:
  - `MONGO_URL`, `DB_NAME`, `CORS_ORIGINS`
  - optional `SOLANA_RPC_URL` (defaults to `https://api.mainnet-beta.solana.com`)

**Frontend (ported pages + design system)**
- ✅ Global CSS in `src/index.css`:
  - variables, themes, scanlines, neural bg, glass cards, buttons, badges
  - animations: fade-ins, live-dot pulse, ticker
  - BASHAM theme overrides
- ✅ Google Fonts included in `public/index.html` (Unbounded, Syne, JetBrains Mono, DM Mono, Manrope, Bebas Neue).
- ✅ Shared layout:
  - sticky nav + mobile menu
  - ticker tape
  - theme switching based on route (`/basham`, `/side-hustle` → BASHAM)

**Solana client support (Withdraw page)**
- ✅ Added CRA-friendly polyfills and CRACO webpack fallbacks for `@solana/web3.js`.
- ✅ Client-signed SOL transfer flow implemented (Phantom required; non-Phantom shows instruction).

**Pages (11 routes) — all implemented**
1. ✅ `/` Command Centre: phases, stats, waveform canvas, events stream, quick actions.
2. ✅ `/yabbai` Token App: OHLCV canvas chart, swap panel, mission phase progress, “Sweep All Yields”.
3. ✅ `/launch` Launch sequence: launchpad selection + mint registration persisted to Mongo.
4. ✅ `/payment` Payment Engine: 12 rails, PayPal autopayout simulation, real vs mock ledger filter.
5. ✅ `/mission` Mission Builder: value locks, sliders, mission plan typewriter generator.
6. ✅ `/wallet` Wallet connect: Phantom connect prompt when available; address lookup and backend balance fetch with demo fallback.
7. ✅ `/withdraw` Withdraw Portal: Phantom-sign transaction UX + treasury balance display.
8. ✅ `/api-pulse` API Pulse: 20 API cards + waveform + cascade mode.
9. ✅ `/basham` Gold Harvester: audit form, wealth map generator (typewriter), colony list.
10. ✅ `/side-hustle` Side Hustle Protocol: signal feed, scripts tab, add lead form.
11. ✅ `/promo` Promo generator: canvas preview, template/theme controls, generation history.

**Data strategy**
- ✅ Simulations in local state + `setInterval`.
- ✅ “Live mode” toggles automatically when `/api/token-mint` returns `configured:true`.

**Phase 2 testing (end-to-end)**
- ✅ Full navigation and key interactions validated across all pages.
- ✅ Backend endpoints validated including input validation and graceful error handling.
- ✅ Test report generated under `/app/test_reports/iteration_1.json`.

---

### Phase 3 — Hardening + Production polish (NEXT)
Goal: reduce warnings, improve resilience/performance, and tighten UX edge cases.

**Engineering hardening**
- [ ] Tighten React hook dependencies (e.g., `Layout.js` exhaustive-deps warning) while preserving behavior.
- [ ] Reduce CRA build warnings where possible (e.g., source-map warnings from dependencies are non-critical, but can be suppressed if desired).
- [ ] Add optional lightweight caching/throttling:
  - cache Jupiter price for N seconds per mint
  - throttle Solana balance calls per address
- [ ] Add global error boundaries and standardized toast/inline error components.

**Performance**
- [ ] Ensure every `setInterval` is cleared on unmount (already done in most pages; re-audit).
- [ ] Optimize canvas redraw loops (cap FPS / pause when tab hidden).

**Security / MVP hygiene**
- [ ] Improve server-side base58 validation for `owner` (balance) in addition to `mint`.
- [ ] Add rate limiting / basic abuse protection (optional) for proxy endpoints.
- [ ] Make CORS origin list environment-driven for production deployments.

**UX polish**
- [ ] Add small “demo vs live” badges and clearer copy when Phantom is not installed.
- [ ] Add “copy address” utilities for treasury/mint addresses.
- [ ] Add loading skeletons for wallet + withdraw balance fetches.

**User stories (Phase 3)**
1. As a user, I get a friendly error if Jupiter/Solana RPC is unavailable.
2. As a user, pages remain smooth (no runaway intervals) after navigation.
3. As a user, I can refresh token mint state and see immediate UI changes.
4. As a developer, I can add new API cards/rails with one-line config edits.
5. As a user, I see consistent visuals/spacing across all pages and breakpoints.

**Phase 3 testing**
- [ ] Regression pass on all 11 routes.
- [ ] Basic performance check (no memory leaks from intervals/raf loops).

---

### Phase 4 — Optional extensions (only after approval)
- [ ] Auth (admin-only mint registration / withdrawal owner mode) if required.
- [ ] Caching layer for Jupiter price + balance (server-side) with TTL.
- [ ] Persist additional settings (theme defaults, mission presets).
- [ ] Export promo frames/settings (download PNG from canvas, store presets).

**User stories (Phase 4)**
1. As an admin, I can protect mint registration behind login.
2. As an admin, I can audit config changes with timestamps.
3. As a user, I see faster price loads via caching.
4. As a user, I can save mission presets and reload them.
5. As a user, I can export promo frames/settings.

---

## 3) Next Actions
1. Phase 3: address remaining lint warning(s) and optional build warning suppression.
2. Add optional caching/throttling for `jupiter-price` + `solana-balance`.
3. Add global error boundary + shared notification pattern.
4. Re-run E2E regression after hardening changes.

## 4) Success Criteria
- ✅ All 11 routes render with correct theme + animations.
- ✅ Mint config persists in Mongo and reliably toggles live mode.
- ✅ `jupiter-price` and `solana-balance` return stable JSON and handle invalid inputs.
- ✅ Withdraw page supports Phantom signing flow when available with clear status steps.
- ✅ E2E regression run passes (currently **100%**).
- Phase 3 completion target:
  - no critical console errors
  - reduced lint warnings
  - improved resilience under network/RPC failures
