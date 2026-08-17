# BUILD

Everything needed to stand this up from an empty machine, in the order that
works, with the failures that cost hours written down next to the step that
causes them.

If you only read one section, read **Gotchas** at the bottom. Every entry there
is something that already went wrong once.

---

## What this is

| | |
|---|---|
| **Backend** | Python 3.12 · FastAPI · Motor · MongoDB |
| **Frontend** | React 19 on Create React App via craco — **JavaScript, no TypeScript** |
| **Chain** | Solana mainnet, read-only. Jupiter for price. |
| **Workflows** | Temporal (Python SDK) — optional, worker only |
| **Hosting** | Render (blueprint) or Netlify (static) + MongoDB Atlas |

Roughly 11,200 lines of JavaScript and 9,800 of Python.

**Two front-ends, one backend.** The isolation between them is a *build-time*
property, not a routing one:

```
token.yabbai.network     npm run build            director console, full app
holders.yabbai.network   npm run build:holders    public, read-only, no admin code
api.yabbai.network       uvicorn server:app       FastAPI
```

These must be **two separate deployments**, not two domains on one. Aliases serve
the same bundle to both hostnames, which ships the entire console to the public.

---

### The other documents

| file | what it holds |
|---|---|
| `FINDINGS_2026_08_17.md` | why things are the way they are, including the bugs that were found and how |
| `MAINNET_READINESS.md` | the seven gaps blocking wallet writes, costed and sequenced |
| `OFFER.md` | what to sell, to whom, for how much |
| `AGENT_SYSTEM_FINDINGS.md` | the earlier audit that removed fabricated figures |

`../yabbai-stablecoin` is a separate repo: fully-reserved stablecoin logic with
the invariant under test. Not imported by this app.

---

## Requirements

- Python 3.12+
- Node 18+ (tested on 24)
- MongoDB 8 (a local binary is fine; Atlas M0 for deployment)
- A Solana RPC endpoint — the public one is **not sufficient**, see below

Optional:

- Temporal CLI, only to run the workflow worker
- Rust + Solana CLI + Anchor — **not yet needed**; required for the on-chain
  program described in `MAINNET_READINESS.md`. None of it is installed.

---

## 1. Configuration

```bash
cp backend/.env.example backend/.env
```

Fill in `MONGO_URL`, `DB_NAME`, `HUB_AUTH_URL`, `SOLANA_RPC_URL`.

> **ASCII only in `.env`.** slowapi builds a starlette Config that reads this
> file with the system codepage, not UTF-8. One em-dash raises
> `UnicodeDecodeError` at import and the server never starts — with no useful
> error pointing at the file.

### RPC: use Helius, not the public URL

Measured against `api.mainnet-beta.solana.com` directly:

| call | public endpoint | needed for |
|---|---|---|
| `getTokenSupply` | works | supply, market cap |
| `getAccountInfo` | works | mint / freeze authority |
| `getBalance` | works | treasury balance |
| `getTokenLargestAccounts` | **HTTP 429** | top-holder concentration |
| `getProgramAccounts` | **refused** | holder count |

With the public endpoint, holder count and concentration render `DATA GAP`. A
Helius-class URL returns all five.

---

## 2. Dependencies

```bash
pip install -r backend/requirements.txt
```

```bash
cd frontend && npm install --legacy-peer-deps
```

`--legacy-peer-deps` is required. react-scripts 5.0.1 mixes two incompatible ajv
generations; the `overrides` block in `package.json` pins ajv@8 globally and
ajv@6 into exactly three subtrees. Do not remove it, and keep eslint on 8.x —
eslint 9 fails the build with `Cannot set properties of undefined`.

---

## 3. Run

**MongoDB first.**

```bash
mongod --dbpath ./mongodb/data --bind_ip 127.0.0.1 --port 27017
```

> On Windows the portable zip needs the Visual C++ runtime present, or
> `mongod.exe` exits with `0xC0000135` before writing any log line.

**API:**

```bash
uvicorn server:app --reload --app-dir backend --port 8000
```

**Front end** — public view:

```bash
cd frontend && npm run start:holders
```

**Front end** — director console:

```bash
cd frontend && npm start
```

> Every console route is wrapped in `ProtectedRoute`, which redirects to the hub
> when there is no session cookie. Running it locally without a hub session
> bounces to `yabbai.network` rather than rendering. The public build has no
> router and no auth, so it always renders.

**Temporal worker** (optional):

```bash
temporal server start-dev
```

```bash
python backend/workflows/worker.py
```

---

## 4. Test

No network, no database:

```bash
python tests/test_performance.py
python tests/test_auth_surface.py
python tests/test_wallet_auth.py
python tests/test_faucet_workflow.py
```

```bash
node ../yabbai-stablecoin/src/invariant-test.js
```

Live mainnet reads (needs network):

```bash
python tests/test_solana_live.py
```

**`test_auth_surface.py` is the important one.** It asserts exactly which routes
are reachable without a session, and it exists because a previous version of this
project was publicly reachable and got swept. If it fails after you add a route,
that is the test working. Add the route to `PUBLIC` only after deciding it belongs
there, and write down why.

---

## 5. Back up

```bash
python scripts/backup_db.py
```

Price and treasury observations are readings of moments that have passed. They
cannot be rebuilt. `backups/` is gitignored — never commit one; git keeps deleted
content forever.

---

## 6. Deploy

**Render blueprint.** Dashboard → Blueprints → New Blueprint Instance → point at
this repo. It creates all three services from `render.yaml`.

Supply in the dashboard (never committed): `MONGO_URL`, `SOLANA_RPC_URL`,
`JUPITER_API_KEY`, `WEBHOOK_SECRET`.

MongoDB Atlas M0, with `0.0.0.0/0` allowed in network access — Render free
instances have no static egress IP.

> **Blueprint services build from `main`.** Work on a feature branch deploys
> nothing. Merge first, or the deploy silently ships the previous app.

---

## 7. Connecting a separate front end

Anything hosted elsewhere — a Next.js dashboard, a v0 build — is a different
origin, so two things must both be true or every call fails.

**Point it at the API, not at localhost.** A deployed page cannot reach
`127.0.0.1`, and an HTTPS page calling `http://` is blocked as mixed content
before the request is even attempted.

```bash
NEXT_PUBLIC_YABBAI_API_URL=https://api.yabbai.network    # deployed
NEXT_PUBLIC_YABBAI_API_URL=http://127.0.0.1:8000         # local only
```

No trailing slash — clients append `/api/...`.

**Add the origin to `CORS_ORIGINS`** and restart the API. Local dev already
allowlists ports 3000 and 4173 on both `localhost` and `127.0.0.1`.

> **Never `*`.** Credentials are allowed on this API, and a wildcard with
> credentials lets any site on the internet make authenticated calls on behalf of
> a signed-in director. The server refuses a wildcard and falls back to the known
> host list, so setting it does not even work — it just fails confusingly.

To expose a local API over HTTPS for a few minutes without deploying:

```bash
cloudflared tunnel --url http://localhost:8000
```

The URL changes on every restart. Testing only.

**Only four endpoints are reachable without a session:**

```
GET /api/public/token           supply, holders, price, market cap, authorities
GET /api/public/price-history   recorded price points
GET /api/faucet/status          claim counts and cap
GET /api/                       health
```

Everything else returns 401. That is the whole surface an external dashboard
gets, deliberately — see `tests/test_auth_surface.py`.

**`NEXT_PUBLIC_` values are compiled into the client bundle and are public.** An
API URL is fine. An RPC key, a webhook secret or anything else is not.

---

## Gotchas

Each of these cost real time at least once.

**The dev server does not watch `public/index.html`.** Edit it and nothing
happens — it looks like a broken change and is a stale server. Restart before
concluding anything.

**`craco build && node scripts/seo.js` breaks on source-map warnings.** `@solana`
packages ship broken source maps; the warnings make craco exit non-zero, the `&&`
stops, and the SEO step silently never runs. `GENERATE_SOURCEMAP=false` fixes it
and also stops publishing your source.

**`cross-env` applies to one command only**, not the whole `&&` chain. It is
repeated after the `&&` in `build:holders` on purpose.

**CSP host matching has no subdomain wildcard.** `https://yabbai.network` does
*not* cover `https://api.yabbai.network`. Omit the second and the browser blocks
every API call — and it surfaces as a CSP violation in the console, not a network
error, so you will look at CORS and the backend for an hour.

**No inline `<script>` in `index.html`.** `script-src 'self'` with no
`unsafe-inline` blocks it, and it works locally because no CSP header is served
there. Put it in `public/` and load it with `src`.

**Wallet detection needs a `CustomEvent`, not an `Event`.** The Wallet Standard
app-ready event must carry `detail` containing `register`. A bare `Event` leaves
it undefined and every extension throws *inside its own injected script*, so the
stack trace points at Phantom or MetaMask and looks like someone else's bug. It
is not. See `frontend/src/lib/wallets.js`.

**Never poll `detectWallets()` on an interval.** It drives that handshake, so a
1-second poll re-runs every installed extension's registration once a second for
as long as the tab is open. Bounded timeouts only.

**The agent pool produces no income.** 255,000+ cycles, $0 booked. It is the
first thing to switch off if CPU matters. The `$0` is not a bug — the ledger
refuses to book income without a verified webhook signature and reports honest
zeros rather than inventing a number.

**`FAUCET_ENABLED` should stay `false` until after graduation.** Free tokens get
sold, and selling into a bonding curve pulls SOL back out of it, moving
graduation further away.
