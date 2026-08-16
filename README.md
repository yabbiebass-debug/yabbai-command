# YABBAI Command

Two front-ends over one FastAPI + MongoDB backend.

| Host | Build | Audience |
|---|---|---|
| `token.yabbai.network` | `npm run build` | Director only — full command centre |
| `holders.yabbai.network` | `npm run build:holders` | Public — read-only token statistics |

**These must be two separate Netlify sites, not two domain aliases on one site.**
Aliases on a single site serve the same bundle to both hostnames, which would ship the
entire command application to the public holder view. The isolation is a build-time
property, not a routing one.

The holders build contains no admin code at all — no `ProtectedRoute`, no Settings, no
Withdraw, no wallet adapter, no auth of any kind. `src/index.js` branches on
`REACT_APP_BUILD_TARGET`, which is a compile-time constant, so webpack eliminates the
untaken branch and everything it imports. Verified: 17 admin markers absent from the
holders bundle, which is 225 KB against the command build's 1,090 KB.

The public page also fetches with `credentials: 'omit'`, so the `.yabbai.network`
session cookie never rides along to the public subdomain.

**Read-only against chain.** The app holds no private keys and signs nothing. The one
place funds move — the treasury sweep — builds a transaction in the browser and hands
it to the operator's wallet extension to sign. Sweep destinations are additionally
restricted to a hardcoded allowlist in `backend/server.py`.

---

## Data policy

Every number shown to a user is read from mainnet, from Jupiter, or measured from
recorded observations. Nothing is projected from a formula.

When a value cannot be read, the UI shows **DATA GAP** and the API returns `null` with
the field named in `data_gaps`. It never substitutes `0`, and it never estimates.

This is not decoration. The app previously displayed APY figures computed as
`risk * 8 + 200` — a linear function of a slider that touched no market — and shipped
promo images asserting "847% APY" and "1,337 holders", both invented. Those are gone.
See [AGENT_SYSTEM_FINDINGS.md](AGENT_SYSTEM_FINDINGS.md).

---

## Requirements

- Python 3.12+
- Node 18+
- MongoDB
- A Solana RPC endpoint (see below — the public one is not sufficient)

## Setup

```bash
cp backend/.env.example backend/.env
```

Fill in `MONGO_URL`, `HUB_AUTH_URL`, and `SOLANA_RPC_URL`, then:

```bash
pip install -r backend/requirements.txt
```

```bash
cd frontend && npm install --legacy-peer-deps
```

## Run

MongoDB first. On Windows the portable zip needs the Visual C++ runtime present, or
`mongod.exe` exits with `0xC0000135` (DLL not found) before writing any log:

```bash
mongod --dbpath ./mongodb/data --bind_ip 127.0.0.1 --port 27017
```

Then the API:

```bash
uvicorn server:app --reload --app-dir backend --port 8000
```

Then the UI:

```bash
cd frontend && npm start
```

Note that every frontend route is wrapped in `ProtectedRoute`, which redirects to the
hub login when there is no session cookie. Running the UI locally without a hub session
will bounce to `yabbai.network` rather than render. The API is testable directly —
`/api/token-stats`, `/api/performance`, `/api/analytics` and `/api/health/details` are
readable without a session, while director-only routes return 401.

Verified working locally against mainnet:

```bash
curl http://127.0.0.1:8000/api/token-stats
```

---

## RPC endpoint: use Helius, not the public URL

`https://api.mainnet-beta.solana.com` is the default when `SOLANA_RPC_URL` is unset, and
it is not adequate. Measured against it directly:

| Call | Public endpoint | Needed for |
|---|---|---|
| `getTokenSupply` | works | supply, market cap |
| `getAccountInfo` | works | mint / freeze authority |
| `getBalance` | works | treasury balance |
| `getTokenLargestAccounts` | HTTP 429 | top-holder concentration |
| `getProgramAccounts` | refused | holder count |

With the public endpoint, holder count and concentration render DATA GAP. A Helius
mainnet URL in `SOLANA_RPC_URL` returns all five.

---

## The endpoints that matter

**`GET /api/token-stats`** — live mainnet facts for the configured mint: supply,
holder count, price, market cap, top-20 concentration, and whether mint and freeze
authority are revoked. Unreadable fields come back `null` and are listed in `data_gaps`.

**`GET /api/performance?window_days=30`** — realised treasury performance measured from
recorded snapshots. Returns `available: false` with a reason when there is not enough
history rather than inventing a figure.

The important detail: a treasury balance moves for two unrelated reasons, performance
and external flows. Depositing 1 SOL into an empty treasury is not a 100% gain. So this
computes:

```
performance = (ending_value - starting_value) - net_external_flows
```

and annualises only when at least 7 days have been observed, labelled as extrapolation.
Covered by `tests/test_performance.py`.

**`POST /api/snapshot/now`** — force an immediate observation instead of waiting for the
poller. Director-only.

A background poller writes a real price and treasury observation every
`SNAPSHOT_INTERVAL_SECONDS` (default 300). Those rows are what `/api/performance`
measures, so performance stays unavailable until the poller has run a few times.

---

## Tests

Performance math — no network needed:

```bash
python tests/test_performance.py
```

Live mainnet reads — needs network. Two checks skip on the public RPC and run when
`SOLANA_RPC_URL` points at a Helius-class endpoint:

```bash
python tests/test_solana_live.py
```

---

## Auth

The command app is a spoke and stores zero credentials. `HUB_AUTH_URL` points at the
hub, which is the sole identity provider. Sensitive routes require
`Depends(require_director)` and fail closed: 503 when `HUB_AUTH_URL` is unset, 401 when
there is no valid session. All frontend routes are wrapped in `ProtectedRoute`.

For cookies to work across both hosts, the hub must set `COOKIE_DOMAIN=.yabbai.network`.

---

## What is not wired

Missions saved in the Mission Builder are configuration records. Nothing reads or
executes them, so they generate no yield, and they are stored with status `saved`
rather than `active`. The agent pool runs orchestrator cycles independently of them.

Connecting the two means executing real trades sized by a risk slider. That is a
decision about real money and is deliberately left un-made.
