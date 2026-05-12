# plan.md — YABBAI (FARM stack port)

## 1) Objectives
- Port the provided TanStack Router reference UI/UX to FARM: **FastAPI + React + MongoDB**.
- Deliver 11 routes with the same simulated “live” feel (interval ticks, waveforms, event streams) and dual themes (**YABBAI** vs **BASHAM**).
- Implement backend APIs:
  - `token-mint` (CRUD, persisted in MongoDB)
  - `jupiter-price` (proxy price lookup)
  - `solana-balance` (proxy on-chain balances)
- Preserve key visual system: ultra-dark (#060E20), Solana Purple/Green, amber, glass/scanlines/neon, fonts, animations.

## 2) Implementation Steps

### Phase 1 — Core POC (Isolation) 
**Core risk:** external integrations + persistence powering “live mode”: MongoDB CRUD + proxy endpoints (Jupiter + Solana RPC).

**Web research (best practices / gotchas)**
- Verify Jupiter price endpoint usage + rate limits; confirm expected response format.
- Verify Solana balance retrieval approach (getBalance + token accounts) and CORS/proxy patterns.

**POC deliverables (backend only + minimal curl tests)**
- FastAPI app runs locally and connects to Mongo.
- Endpoints:
  1. `GET /api/token-mint` returns `{configured:false}` when empty.
  2. `POST /api/token-mint` upserts mint config.
  3. `DELETE /api/token-mint` clears record.
  4. `GET /api/jupiter-price?mint=...` returns `{ok:true, price:number|null}`.
  5. `GET /api/solana-balance?owner=...` returns `{ok:true, sol:number, tokens:[...]}`.
- Add a single Python script `scripts/poc_core.py` that:
  - writes token mint config
  - reads it back
  - calls Jupiter price for SOL mint
  - calls Solana balance for a known public address

**User stories (Phase 1)**
1. As a developer, I can run one script that proves Mongo persistence and both proxies work.
2. As a developer, I can clear/reset mint config without restarting services.
3. As a developer, I can observe stable JSON shapes for frontend consumption.
4. As a user, I can see “pre-launch” vs “live” controlled solely by mint config.
5. As a developer, failures return clear `{ok:false,error}` without crashing.

**Exit criteria (must pass before Phase 2)**
- POC script completes successfully twice in a row.
- Mongo record persists across server restart.
- Proxy endpoints handle invalid inputs gracefully.

---

### Phase 2 — V1 App Development (Frontend + Backend wiring)

**Repo structure / wiring**
- Backend: FastAPI under `/app/backend` with routers under `/api`.
- Frontend: React under `/app/frontend` using React Router DOM.
- Configure dev proxy (`/api/*`) from frontend to backend.

**Backend (MVP)**
- Mongo model/collection: `token_mint_config` with fields: `configured, mint, decimals, supply, treasury, mainWallet, network, launchpad, tx, launchedAt`.
- Implement routes:
  - `GET/POST/DELETE /api/token-mint`
  - `GET /api/jupiter-price`
  - `GET /api/solana-balance`
- Centralized settings (env): `MONGODB_URI`, optional `SOLANA_RPC_URL`.

**Frontend (port pages 1:1 from reference)**
- Add global CSS (port from `styles.css`) into `src/index.css` with:
  - variables, themes, scanlines, neural bg, glass cards, buttons, badges
  - animations: fade-ins, live-dot pulse, ticker
  - BASHAM theme overrides
- Add Google Fonts in `public/index.html`.
- Add shared layout:
  - sticky nav + mobile menu
  - ticker tape
  - theme switching based on route (`/basham`, `/side-hustle` => BASHAM)

**Pages (11 routes)**
1. `/` Command Centre: phases, stats, waveform canvas, events stream, quick nav cards.
2. `/yabbai` Token App: OHLCV canvas chart, simulated price OR live via backend, swap panel + optional iframe when mint configured.
3. `/launch` Launch sequence: mint registration -> persists to Mongo; polling Jupiter price for “takeoff”.
4. `/payment` Payment Engine: 12 rails, PayPal autopayout simulation, real vs mock ledger separation.
5. `/mission` Mission Builder: value locks, sliders, mission plan typewriter generator.
6. `/wallet` Wallet connect: Phantom connect when available; demo fallback; call `/api/solana-balance` for live reads.
7. `/withdraw` Withdraw Portal: keep @solana/web3.js flow; ensure safety messaging; use backend for any needed config only (withdraw stays client-signed).
8. `/api-pulse` API Pulse: 20 API cards + waveform + cascade.
9. `/basham` Gold Harvester: audit form, wealth map generator, colony list.
10. `/side-hustle` Side Hustle Protocol: lead board + signal feed + scripts modal.
11. `/promo` Promo generator: 1:1 frame with canvases.

**Data strategy**
- Keep simulations in local state + `setInterval` as in reference.
- “Live mode” toggles automatically when `/api/token-mint` returns `configured:true`.

**User stories (Phase 2)**
1. As a user, I can open Command Centre and see live-feeling stats/events instantly.
2. As a user, I can register a mint on Launch and the whole app flips to live pricing.
3. As a user, I can view Wallet balances via Phantom or demo mode fallback.
4. As an owner, I can initiate a withdrawal and see clear signing/broadcast/confirm states.
5. As a user, I can switch between YABBAI and BASHAM experiences by navigating pages.

**Phase 2 testing (end-to-end)**
- Run through: Home → Launch register mint → YABBAI live price fetch → Wallet connect/demo → Withdraw demo path → API Pulse cascade → BASHAM pages.
- Verify CSS/animations on mobile breakpoints.

---

### Phase 3 — Hardening + Production polish
- Error handling + loading states across all pages (especially launch/live polling, balance fetch).
- Performance: throttle intervals, cancel animations on unmount, reduce canvas redraw cost.
- Security/MVP hygiene:
  - validate base58 addresses server-side (mint/owner)
  - timeouts + retries for proxy endpoints
  - CORS config for deployment
- Refactor repeated UI into small components (Card, Badge, Button, Toggle, Stat).

**User stories (Phase 3)**
1. As a user, I get a friendly error if Jupiter/Solana RPC is unavailable.
2. As a user, pages remain smooth (no runaway intervals) after navigation.
3. As a user, I can refresh token mint state and see immediate UI changes.
4. As a developer, I can add new API cards/rails with one-line config edits.
5. As a user, I see consistent visuals/spacing across all pages and breakpoints.

**Phase 3 testing**
- Regression pass on all 11 routes; verify “live mode” and “pre-launch mode”.

---

### Phase 4 — Optional extensions (only after approval)
- Auth (admin-only mint registration / withdrawal owner mode) if required.
- Caching layer for Jupiter price + balance.
- Persist additional settings (theme defaults, mission presets).

**User stories (Phase 4)**
1. As an admin, I can protect mint registration behind login.
2. As an admin, I can audit config changes with timestamps.
3. As a user, I see faster price loads via caching.
4. As a user, I can save mission presets and reload them.
5. As a user, I can export promo frames/settings.

## 3) Next Actions
1. Implement Phase 1 backend endpoints + Mongo connection.
2. Add `scripts/poc_core.py` and run until green.
3. Port global CSS + fonts into React template.
4. Port routes/pages in bulk (copy reference logic, replace fetch URLs to `/api/*`).
5. Run one E2E pass and fix breakages before any enhancements.

## 4) Success Criteria
- All 11 routes render with correct theme + animations and no console errors.
- Mint config persists in Mongo and reliably toggles live mode.
- `jupiter-price` and `solana-balance` return stable JSON and handle invalid inputs.
- Withdraw page can complete demo path and real Phantom path (when available) with clear status steps.
- One full regression run passes without broken navigation, runaway intervals, or layout issues.
