# The thing you can sell on Monday

Written 17 Aug 2026. This is not a business plan. It is the shortest honest route
from $0 to a first invoice, using only what already exists in this repo.

## What you actually have

Not a token. A working system that most Solana projects need and almost none
build, because building it costs weeks and lying costs nothing.

- Live mainnet reads that survive an RPC provider refusing methods on plan
  grounds, with a fallback chain that remembers which endpoint declined what
- Treasury performance that subtracts external flows, so depositing 1 SOL into
  an empty treasury is not reported as a 100% gain
- `DATA GAP` instead of a substituted zero, everywhere
- A public holder page that ships 239 KB with zero admin code compiled into it
- An auth surface asserted by a test, not by hope
- Buyback quoting through real Jupiter routes, signed by the operator's own
  wallet, with the server holding no key

Any one of those is a week of work. Together they are the thing a project reaches
for the day someone in their Telegram asks "how do we know these numbers are
real?"

## Who pays for it

Projects that have just been accused of faking numbers, or that expect to be.
Specifically:

1. **Post-graduation tokens with a community.** They have holders asking
   questions and a market cap worth defending. A public stats page they did not
   write themselves is evidence.
2. **Projects that got called out.** Someone posted their invented APY. They need
   a verifiable page yesterday.
3. **Launchpad and tooling teams.** They need holder-facing analytics for many
   mints and would rather buy than build.

You are not selling analytics. Analytics are free on Dexscreener. You are selling
**a page that says DATA GAP** — the credible refusal to invent a number. That is
the product, and it cannot be copied by anyone unwilling to lose by it.

## The offer, three tiers

Priced for a first customer, not for a business you do not have yet. Low enough
that saying yes is easy, high enough that it is real money.

**Tier 1 — Hosted holder page. $150 setup + $30/month.**
Their mint, their branding, your stack. Live supply, holders, price, market cap,
concentration, authority status, curve progress. DATA GAP where the chain will
not answer. Deployed on a subdomain they control.
*Your cost: change one env var, one deploy. Under an hour after the first.*

**Tier 2 — Page plus treasury reporting. $400 setup + $60/month.**
Everything above plus treasury snapshots and realised performance measured
against recorded observations, with external flows subtracted. This is the part
nobody else does correctly, and it is the part that ends arguments.
*Your cost: one poller, config already written.*

**Tier 3 — Audit and write-up. $600, one off.**
You go through their public numbers and report which are read from chain, which
are computed, and which are invented. Deliverable is a document they can publish.
Some will not want the answer. The ones who do will pay for it, and they are the
better customers anyway.
*Your cost: a day. You have already done this to yourself — see
AGENT_SYSTEM_FINDINGS.md, where you found `risk * 8 + 200` being served as an APY.*

## What to say

No pitch deck. One message, sent to a project that has holders and a public page:

> Your stats page shows [specific number]. I checked it against chain and it
> reads [what you actually found]. I built the same thing for my own token and
> made it show DATA GAP rather than guess — [holders.yabbai.network]. If you want
> one that holders can verify themselves, I can have it up on your mint this
> week for $150.

That works because it is not a pitch. It is a free piece of real work handed over
first, which is also the only credible way to prove you check things.

Send five. Expect one reply. That is normal and is not a verdict on the work.

## Before invoicing anyone

- **`WEBHOOK_SECRET` must be set** on the API, and the same value configured as
  the signing secret in Stripe or Gumroad. Until then `real_income()` books
  nothing and your ledger keeps reporting $0 — correctly, because verification
  fails closed by design.
- Invoice in AUD, register an ABN, keep receipts. Sole trader is enough to start.
- This is services income, not a financial product. No AFSL question arises,
  because you are selling software work and not an investment. Keep it that way:
  do not accept your fee in tokens, and do not price it against the token.

## Why this beats waiting for the token

Graduation needs 998 SOL ≈ $75,500 of net buying. Nothing you control produces
that on a schedule.

Four Tier 1 customers is $600 setup and $120/month, and it depends on nobody's
speculation. It also does the thing waiting cannot: it puts your work in front of
projects that have holders, which is the only place your own holders four and
five were ever going to come from.

The token can still run. This just means you eat either way.
