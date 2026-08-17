# Mainnet readiness — what actually closes each gap

Seven items block safe wallet writes. They are not the same size, they do not
cost the same, and two of them cannot be closed by writing code. Sequenced so
each step is useful even if you stop after it.

**Nothing here is optional if real money moves.** The gate is correct; this is
how to open it honestly rather than how to bypass it.

---

## The seven, sized

| # | gap | closed by | who | cost |
|---|---|---|---|---|
| 1 | No deployed program | Anchor program + deploy | me, then you | ~3 SOL rent |
| 2 | No verified program ID / IDL | falls out of 1 + verified build | me | free |
| 3 | No redemption mechanism | part of the program | me | free |
| 4 | No reserve attestation | reserve as a PDA | me | free |
| 5 | No oracle policy | Pyth + staleness rules | me | free |
| 6 | **No contract audit** | **third-party firm** | **not me** | **$10k–50k+** |
| 7 | No mainnet test suite | devnet integration + mainnet reads | me | free |

Five of seven are work I can do. One needs your keys and about 3 SOL. **One needs
money and a stranger, and it is the one that matters most.**

---

## 1–3. The program (these are one job)

Currently the mint authority is a keypair on a laptop. The reserve rule in
`yabbai-stablecoin/src/reserve.js` holds only while the script chooses to behave,
and a script can be edited. That is the whole difference between this and a
stablecoin.

**The fix:** an Anchor program owning the mint authority via PDA, checking the
reserve *inside the same transaction* that mints. Then nobody can mint unbacked —
not you, not someone who takes your keys, not a compromised server.

Instructions needed:

```
initialize    create reserve PDA, set peg, set oracle, revoke external mint authority
deposit       take collateral into the PDA, mint at peg, atomically
redeem        burn tokens, release collateral at peg, atomically   <- gap 3
pause         halt mint+redeem; redeem-only mode for wind-down
```

The invariant is already written and tested in `reserve.js` — the 14 tests are
the specification. Porting it to Rust is transcription against a spec, not
design, which is the cheapest kind of on-chain work there is.

**Toolchain is not installed here.** Nothing in the Solana chain is present:

```
rustc   not installed
cargo   not installed
anchor  not installed
solana  not installed
```

Rust plus the Solana CLI and Anchor is a multi-GB install and a long first build.
That is a fresh-morning job, not a 11:45pm one.

**Gap 2 falls out for free** once the program exists: `anchor build` emits the
IDL, and a verified build (`solana-verify`) lets anyone confirm the deployed
bytecode matches this repo. Publish the IDL on-chain so explorers decode your
instructions instead of showing opaque bytes.

---

## 4. Reserve attestation — the cheap win

This is the one people assume is expensive and is not.

Fiat-backed stablecoins need an accountant's attestation because the dollars sit
in a bank nobody can see. **Yours does not have that problem.** If the reserve is
a PDA holding SOL or USDC, then:

- anyone can read the balance directly from chain, any time
- anyone can read circulating supply from the mint
- the ratio is computable by a stranger with no trust in you at all

That is a *stronger* attestation than a quarterly PDF, and it costs nothing. Put
`reserve_balance`, `circulating_supply` and `collateral_ratio` on the holders
page reading straight from chain, and the attestation problem is solved
permanently.

**Do not hold the reserve in a wallet you control.** The moment reserves sit in
an operator keypair rather than a program-owned PDA, attestation becomes a
promise again and you are back to needing a third party.

---

## 5. Oracle policy

Jupiter is a price API, not an oracle. Fine for a dashboard, not for deciding how
many tokens a deposit backs — one bad quote at the wrong moment mints unbacked
supply, permanently.

**Policy to implement in the program:**

| rule | value | why |
|---|---|---|
| Source | Pyth SOL/USD on-chain | signed, on-chain, aggregated |
| Max staleness | 60 seconds | a stale price is a wrong price |
| Confidence bound | reject if `conf/price > 2%` | wide confidence = unreliable |
| Deviation guard | reject if >10% from last accepted | catches manipulation |
| Fallback | **refuse the transaction** | never guess |

That last row is the important one. A stablecoin that keeps minting when it
cannot price collateral is how the whole thing unwinds. Refusing is the correct
behaviour, and it matches what the app already does everywhere else — `DATA GAP`
rather than a substituted number.

**Prefer USDC collateral over SOL.** A USDC-collateralised coin barely needs an
oracle at all, since the collateral is already denominated in the peg currency.
Test 5 in the invariant suite demonstrates exactly why volatile collateral breaks
pegs — nothing is minted wrongly, the collateral simply becomes worth less than
the promise written against it.

---

## 6. Audit — the one that costs money

**Cannot be done by me, and cannot be done cheaply.** An audit is a stranger with
no stake in it passing, paid enough to be thorough, who reads the code trying to
break it. Self-review does not substitute, and neither does another model
reviewing my work — we share failure modes.

Realistic range for a small Anchor program: **$10k–50k+**, weeks of lead time.

Cheaper ladder, in order, if that is out of reach:

1. **Publish the program source** and the verified build hash. Free. Lets anyone check.
2. **Deploy with a low supply cap** — a hard ceiling on total mint. Bounds the worst case to a number you can afford to lose.
3. **Bug bounty** before the cap lifts. Pay for the finding, which is far cheaper than paying for the incident.
4. **A single reviewer** from the Solana community for a few hundred dollars. Weaker than a firm, much stronger than nobody.
5. **Then** the full audit, funded from actual revenue.

The supply cap is the one to do regardless. An unaudited program holding $500 is
a bad week. The same program holding $500,000 is the end of the project.

---

## 7. Test suite

Three layers, none of which need a mainnet deploy to write:

```
unit        the invariant, already 14/14 in reserve.js
integration anchor test on a local validator: deposit, redeem, over-mint refused,
            stale oracle refused, paused state, cap enforced
mainnet     read-only assertions against the deployed program — supply matches
            reserve, authority is the PDA, ratio >= 1.0, run on a schedule
```

The third layer is the one that catches drift after launch, and it is the one
everybody skips. It is also the cheapest, because it only reads.

---

## Sequence

1. Install Rust + Solana CLI + Anchor *(morning job, long download)*
2. Port the invariant to an Anchor program, with a supply cap *(1–2 days)*
3. Integration tests on a local validator *(same day)*
4. Pyth oracle with the policy above *(half a day)*
5. Deploy to **devnet**, run everything against it *(hours)*
6. Publish source + verified build, IDL on-chain *(hours)*
7. Reserve ratio live on the holders page, read from chain *(hours)*
8. Supply cap set low. Bug bounty posted.
9. Mainnet deploy — ~3 SOL, your keys, your call
10. Audit when revenue allows. Raise the cap only afterwards.

Steps 1–8 are work, not money. Step 9 is about 3 SOL. Step 10 is the expensive
one and it belongs after there is something worth auditing.

---

## Until then

**Keep wallet writes gated.** The tool that flagged this was right, and it
reached the same conclusion independently of the session that built the app —
which is worth more than either judgement alone.

The read-only dashboard is not a lesser product. It is the honest one, and it is
already the thing nobody else in this space is shipping.
