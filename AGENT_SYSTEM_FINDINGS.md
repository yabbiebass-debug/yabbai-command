# Findings and Fixes

**Date:** 2026-08-16
**Scope:** backend agents, compliance gates, live Solana data, frontend metrics, build toolchain

---

## Part 1 — The APY numbers were a slider formula

The dashboard figures measured nothing. `Mission.js` computed:

```js
estimated_apy: Math.round(config.risk * 8 + 200)
```

A linear function of the risk slider, reading no price, no pool, and no fill. The four
missions on the board mapped exactly onto four slider positions:

| Mission | Displayed APY | Slider value |
|---|---|---|
| Liquidity Mining Protocol | 600% | risk = 50 |
| Yield Aggregator Strategy | 640% | risk = 55 |
| MEV Arbitrage Bot | 672% | risk = 59 |
| Token Launch Scout | 680% | risk = 60 |

`risk * 8 + 200` reproduces all four exactly. Two further cards were the same trick:
daily yield was `autonomy * 2.8 + 50`, max drawdown was `risk * 0.3`.

Because these were disconnected from any market, they could not hit a liquidity ceiling
or a slippage wall. Advice framing them as returns to be throttled or sequenced was
solving a problem that did not exist.

## Part 2 — The agents generated exactly zero, by construction

`revenue_generated` accumulated only when a phase returned a positive
`revenue_generated`. The sole phase returning that key, `phase_mission`, returned a
hardcoded `0.0`. The opportunity scanners returned fixed literals (`$97`, `$2500`, `$50`)
marked `# Placeholder`; `phase_esky` set `leads_generated = 10  # Simulated for now`.

"50 agents" came from `target_agents_per_phase=10` × 5 phases. Every agent walked all
five phases each cycle regardless of assignment, so the phase labels carried no meaning.

---

## Bugs fixed

### `agent_pool.py` — `NameError` silently killed status persistence
`agent_supervisor()` referenced `now` without defining it. Every 60s this raised, was
swallowed by the bare `except`, and logged as "Agent supervisor error", so
`agent_pool_status` was **never written**. Any dashboard reading it showed stale data
indefinitely.

### `agent_pool.py` / `cycle_agent.py` — phase drift leaked the pool until it jammed
`run_cycle()` overwrites `self.current_phase` as it walks phases, ending on `WITHDRAW`.
`terminate_agent()` then discarded the id from the **wrong** phase set, so ids
accumulated in `PUMP`/`ESKY`/`MISSION`/`SCALE` forever. Since `spawn_agent()` refuses
once a phase holds `max_agents_per_phase` (15), those phases would permanently stop
respawning while still reporting healthy counts. Fixed with an immutable `home_phase`
for bookkeeping; crashed agents are now removed from tracking rather than leaked.

### `Promo.js` — fabricated investment claims exported to public images
`COPY_LINES` contained `'847% APY — AI-powered treasury management'` and
`'Join 1,337 holders earning passive income'`. Both numbers were invented; nothing
computed either. `handleExportPng` renders the selected copy to a canvas and downloads a
PNG for social distribution, so these went out as public claims about token returns.

`compliance_gate.py` existed to stop exactly this, but promo art is generated and
exported entirely client-side and never reaches the backend, so the gate was unenforced
on the one surface facing the public. Both lines removed; a client-side `checkClaims`
mirroring the backend patterns now blocks generate and export.

### `compliance_gate.py` — the gate missed yield and holder claims
`847% APY` passed every existing pattern, and the customer-count pattern required the
literal word "customers", so `1,337 holders` passed too. Added patterns for percentage
yield claims and holder/investor/member/user counts. Verified: both removed lines are
blocked, all three retained lines pass, no false positives.

### `requirements.txt` — missing `slowapi`
`server.py:6` imports `slowapi`, which was never declared. A clean deploy crashed on
startup with `ModuleNotFoundError`. Added.

---

## Part 3 — Real mainnet data

### `backend/solana_live.py` (new)
Read-only mainnet client. Every method returns a real value or `None`; there are no
defaults and no estimates. Provides token supply, mint/freeze authority, largest
accounts, holder count, SOL balance, and token holdings, across both the classic token
program and Token-2022.

Holder count uses `getProgramAccounts` with a `dataSlice` so only the 8-byte amount
field crosses the wire rather than every full account.

Verified against mainnet using USDC, whose values are independently checkable:

```
token_supply    : 7,703,218,947.493172  (decimals 6)
mint_authority  : BJE5MMbq...  freeze: 7dGbd2QZ...
jupiter_price   : 0.9996160230246527
sol_balance     : 1689.901907021
```

The two calls the public RPC refused returned `None` and surfaced as unavailable rather
than as a number. That behaviour is the point.

### `backend/performance.py` (new)
Realised treasury performance, replacing the projected-APY formula.

The correctness point: a treasury balance moves for two unrelated reasons, performance
and external flows. Depositing 1 SOL into an empty treasury is not a 100% gain. So:

```
performance = (ending_value - starting_value) - net_external_flows
```

Annualisation is withheld below 7 observed days, and labelled an extrapolation above it.
When history is insufficient the API returns `available: false` with a reason rather
than a number. Covered by `tests/test_performance.py` — 9 assertions, all passing,
including that a deposit yields 0% and a withdrawal yields 0%.

### New endpoints
- `GET /api/token-stats` — live supply, holders, price, market cap, top-20
  concentration, mint/freeze revocation. Unreadable fields are `null` and named in
  `data_gaps`.
- `GET /api/performance?window_days=30` — realised performance as above.
- `POST /api/snapshot/now` — force an immediate observation (director-only).

A background poller records a real price and treasury observation every
`SNAPSHOT_INTERVAL_SECONDS` (default 300). Its writes match the existing manual
snapshot schema exactly — same `address` field, same datetime type, same 500-row
retention — so both producers populate one consistent collection.

### Frontend
- Mission Builder: projected-APY banner replaced with a realised-performance panel that
  renders DATA GAP when there is no history. The `PROJECTED METRICS` card (APY, daily
  yield, max drawdown) is replaced by the actual configuration values.
- Missions now save with status `saved`, not `active`; nothing executes them, so
  "active" was a false claim.
- Analytics: `APY EST` column replaced with reinvest rate.
- Token page: new on-chain panel showing supply, holders, market cap, concentration and
  authority status, each falling back to DATA GAP individually.

Remaining `Math.random()` calls are cosmetic only (particle positions, console typing
delays) and were already commented as such.

---

## Part 4 — Build toolchain

The frontend did not build at all before these fixes.

**ajv split-brain.** `react-scripts@5.0.1` mixes two incompatible ajv generations.
`schema-utils@4` + `ajv-keywords@5` need ajv@8, or the build dies with
`Cannot find module 'ajv/dist/compile/codegen'`. But `fork-ts-checker-webpack-plugin`,
`babel-loader` and `file-loader` each bundle `ajv-keywords@3`, which reads ajv@6
internals and throws `Cannot read properties of undefined (reading 'date')` under ajv@8.
Resolved with ajv@8 globally and ajv@6 nested into exactly those three subtrees.

**eslint 9 vs CRA 5.** `react-scripts@5.0.1` depends on eslint `^8.3.0` and
`eslint-webpack-plugin@3` peers `^7||^8`, but the project pinned eslint `9.23.0`. That
fails with `Cannot set properties of undefined (setting 'defaultMeta')`. Pinned to
`^8.57.1`.

**Dead TypeScript checker.** The project has no `tsconfig.json` and zero `.ts`/`.tsx`
sources, so `ForkTsCheckerWebpackPlugin` checked nothing while costing build time. Now
filtered out in `craco.config.js`.

---

## Part 5 — Operational finding: the public RPC is not sufficient

Measured directly against `https://api.mainnet-beta.solana.com`, which is the default
when `SOLANA_RPC_URL` is unset:

| Call | Public endpoint | Needed for |
|---|---|---|
| `getTokenSupply` | works | supply, market cap |
| `getAccountInfo` | works | mint / freeze authority |
| `getBalance` | works | treasury balance |
| `getTokenLargestAccounts` | HTTP 429 | top-holder concentration |
| `getProgramAccounts` | refused | holder count |

Holder count and concentration will show DATA GAP until `SOLANA_RPC_URL` points at a
Helius (or equivalent) mainnet endpoint. See `backend/.env.example`.

---

## Not changed, deliberately

**Missions are still not wired to execution.** Connecting them means placing real trades
sized by a risk slider. That is a decision about real money, not a cleanup, and it is
left un-made.

**No private keys anywhere.** `Withdraw.js` builds a `SystemProgram.transfer` and calls
`solana.signTransaction`, so a browser wallet signs and the operator approves. Sweep
destinations are restricted to a hardcoded allowlist. Combined with hub SSO, the app
holds zero credentials. This design is correct and was left alone.

---

## Verification

All checks below were run, not assumed. Python 3.12.10 and Node 24.19.0 were installed
into this environment to make that possible.

| Check | Result |
|---|---|
| Python syntax, all 6 edited files | pass |
| `server.py` imports; 3 new routes registered | pass |
| `tests/test_performance.py` (9 assertions) | pass |
| `tests/test_solana_live.py` against live mainnet | pass (8 pass, 2 skip) |
| Banned-claim regexes vs removed/retained copy | pass |
| Frontend production build, linting enabled | pass (306.49 kB gzipped) |

The 2 skips are `largest_accounts` and `holder_count`, which the public RPC refuses.
They are reported as skipped rather than passed, and run against a Helius endpoint.

**Not verified:** no end-to-end run against a live MongoDB, and no browser test of the
new panels rendering. Both need a database and an RPC key this environment does not
have. The API shapes and the data layer are tested; the wiring between them and the DOM
is not.
