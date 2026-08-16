#!/usr/bin/env python3
"""
YABBAI — system knowledge.

Grounding context handed to any model the hub routes for us. Its job is to stop
generated text from reinventing the things this project spent its time removing:
projected APY presented as return, saved missions described as executing, agent
cycles described as earning.

Everything here is a statement of fact about the system as built, verified against
the code and against mainnet. If the system changes, this must change with it —
stale grounding is worse than none, because it is confidently wrong.
"""

from typing import Any, Dict, List, Optional

TOKEN_FACTS = {
    "name": "YabbAI Token",
    "symbol": "YABBAI",
    "chain": "Solana mainnet-beta",
    "launchpad": "Jupiter Studio",
    "supply": 1_000_000_000,
    "decimals": 6,
    "mint_authority": "revoked",
    "freeze_authority": "revoked",
}

SYSTEM_TRUTHS = [
    "Supply, price, holder count, concentration, authority status and treasury "
    "balances are read live from Solana mainnet and Jupiter. They are measurements, "
    "not estimates.",

    "Saved missions are configuration records. Nothing reads or executes them, so "
    "they generate no yield. Describing a mission as active, running or earning is "
    "false.",

    "The agent pool cycles through phases and reports $0.00 revenue. That is "
    "correct, not a bug: no phase places a trade or collects a fee. Cycle counts "
    "measure activity, never income.",

    "APY was previously displayed as risk * 8 + 200, a function of a slider that "
    "touched no market. It has been removed. Never present a projected figure as a "
    "return.",

    "Treasury performance is measured from recorded snapshots with external flows "
    "backed out, so a deposit is not counted as a gain. It is withheld entirely "
    "when there is not enough history.",

    "Where a value cannot be read, the interface shows DATA GAP. Substituting a "
    "number for an unavailable one is prohibited.",

    "The application holds no private keys. Treasury sweeps are built in the "
    "browser and signed by the operator's own wallet, and destinations are "
    "restricted to a hardcoded allowlist.",

    "holders.yabbai.network is public and contains no admin code. "
    "token.yabbai.network is director-only behind hub SSO.",

    "Marketing copy must not assert yields, earnings, holder counts or guarantees. "
    "A compliance gate blocks those patterns on both the client and the server.",
]

# Statements that must never appear in generated output, with the reason. Useful
# both as instruction and as a post-generation check.
PROHIBITED_CLAIMS = [
    ("guaranteed returns", "no return is guaranteed and saying so is a securities risk"),
    ("missions are executing", "nothing executes saved missions"),
    ("agents are earning", "the agent pool produces $0.00 by construction"),
    ("projected APY as actual", "projections are not measurements"),
    ("invented holder counts", "holder count is read from chain or shown as DATA GAP"),
]


def system_prompt(live_stats: Optional[Dict[str, Any]] = None) -> str:
    """Grounding prompt. Pass live stats to anchor it to current chain state."""
    lines: List[str] = [
        "You are assisting inside YABBAI Command, a Solana treasury dashboard.",
        "",
        "TOKEN",
    ]
    for k, v in TOKEN_FACTS.items():
        lines.append(f"  {k}: {v}")

    if live_stats:
        lines.append("")
        lines.append("CURRENT ON-CHAIN STATE (read live; may be stale by up to a minute)")
        for key in (
            "price_usd", "market_cap_usd", "holders", "top_concentration_pct",
            "treasury_sol", "treasury_token_balance",
        ):
            if key in live_stats:
                value = live_stats[key]
                lines.append(f"  {key}: {value if value is not None else 'DATA GAP'}")
        gaps = live_stats.get("data_gaps")
        if gaps:
            lines.append(f"  unavailable right now: {', '.join(gaps)}")

    lines += ["", "HOW THIS SYSTEM ACTUALLY WORKS"]
    lines += [f"  - {t}" for t in SYSTEM_TRUTHS]

    lines += [
        "",
        "RULES FOR ANYTHING YOU WRITE",
        "  - State only what the data supports. If a figure is unavailable, say so.",
        "  - Never invent a number. DATA GAP is an acceptable answer.",
        "  - Never describe projections, targets or estimates as achieved results.",
        "  - Never claim missions execute or that agents earn.",
        "  - Do not write marketing claims about yield, income or holder counts.",
        "  - Being accurate matters more than being impressive.",
    ]
    return "\n".join(lines)


def agent_prompt(phase: str, live_stats: Optional[Dict[str, Any]] = None) -> str:
    """Grounding for an agent running a specific phase."""
    phase_briefs = {
        "pump": "Identify revenue opportunities. You are producing analysis for a "
                "human to act on, not executing anything.",
        "esky": "Outreach planning. Outbound must satisfy the compliance gate: "
                "opt-in or compliant cold source, working unsubscribe, no fabricated claims.",
        "mission": "Saved missions are configuration only. Report on them as "
                   "configuration; do not describe them as running.",
        "scale": "Assess which channels show measured positive return. Absent "
                 "measured data, say there is none.",
        "withdraw": "Withdrawals are proposed for human approval and restricted to "
                    "an allowlist. You never move funds.",
    }
    brief = phase_briefs.get(phase, "Report factually on the current state.")
    return (
        f"{system_prompt(live_stats)}\n\n"
        f"CURRENT PHASE: {phase}\n  {brief}\n\n"
        "Output analysis a human can verify. Label every figure as measured or "
        "unavailable. Do not produce revenue estimates presented as earnings."
    )


def check_output(text: str) -> List[str]:
    """Flag generated text that contradicts the grounding. Empty means clean."""
    import re

    issues: List[str] = []
    low = (text or "").lower()

    patterns = [
        (r"guaranteed\s+(returns?|profit|income)", "asserts guaranteed returns"),
        (r"\d[\d,.]*\s*%\s*(apy|apr)", "states an APY/APR figure"),
        (r"missions?\s+(are\s+)?(executing|running|earning|active)", "claims missions execute"),
        (r"agents?\s+(are\s+)?(earning|generating revenue|profitable)", "claims agents earn"),
        (r"\d[\d,.]*\s+holders", "states a holder count in prose"),
        (r"risk[- ]?free", "claims risk-free"),
    ]
    for pattern, label in patterns:
        if re.search(pattern, low):
            issues.append(label)
    return issues
