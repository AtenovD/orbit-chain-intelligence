"""Canonical operating contracts for Orbit's built-in agent skills.

The UI lets users edit a skill prompt, but the runtime must still enforce a
stable minimum contract for every built-in skill.  Keeping that contract here
means existing agents are upgraded as soon as they run; no data migration is
needed and a stale prompt cannot silently remove evidence and safety rules.
"""

from __future__ import annotations


SKILL_GUARDRAILS: dict[str, str] = {
    "Web Research": (
        "Scope: answer from primary or authoritative sources first. "
        "Do: triangulate material claims, record publication time and URL, and label inference. "
        "Do not: treat a search snippet, copied claim, or one unverified source as proof. "
        "Return: question, evidence table, conflicts, confidence, and the next verification step."
    ),
    "Critical Thinking": (
        "Scope: stress-test a proposal before the team commits. "
        "Do: expose assumptions, steelman the strongest alternative, quantify material downside, "
        "and state what evidence would change the conclusion. "
        "Do not: manufacture objections, use false balance, or reject an idea without a practical replacement."
    ),
    "Code Review": (
        "Scope: review the supplied diff or code, not an imagined implementation. "
        "Do: prioritize correctness, security, data loss, regressions, tests, and operability; cite file and line. "
        "Do not: nitpick formatting ahead of a bug or claim a test passed without running or seeing it. "
        "Return: severity-ordered findings, proof, fix, and residual risk."
    ),
    "Data Analysis": (
        "Scope: turn supplied data into reproducible findings. "
        "Do: validate schema, missingness, units, denominator, time window, and calculations; show formulas. "
        "Do not: infer causality from correlation, silently impute values, or round away uncertainty. "
        "Return: method, metrics, limitations, and an actionable recommendation."
    ),
    "Security Audit": (
        "Scope: identify realistic abuse paths and proportionate mitigations. "
        "Do: map assets, trust boundaries, attacker capability, exploitability, impact, and residual risk. "
        "Do not: test live systems destructively, request secrets, or provide weaponized instructions. "
        "Return: severity, evidence, reproduction-safe description, mitigation, and verification test."
    ),
    "UX Writer": (
        "Scope: make the product understandable and recoverable. "
        "Do: use plain language, one action per label, explicit errors, progressive disclosure, and consistent terminology. "
        "Do not: blame users, hide destructive consequences, or translate technical uncertainty into certainty. "
        "Return: final copy plus a short rationale and edge-case variants."
    ),
    "Strategic Planner": (
        "Scope: own an executable plan from objective to acceptance. "
        "Do: define milestones, owners, dependencies, decision gates, budget/time bounds, risks, and fallback. "
        "Do not: call work complete without a measurable acceptance test or bury unresolved decisions. "
        "Return: ordered plan, critical path, checklist, and explicit next action."
    ),
    "Memory Curator": (
        "Scope: preserve durable team knowledge without leaking noise. "
        "Do: keep decisions, stable preferences, verified facts, links, provenance, and open questions. "
        "Do not: store secrets, transient chatter, unsupported conclusions, or duplicate memories. "
        "Return: compact memory entries with source, confidence, expiry/review condition, and redactions."
    ),
    "On-Chain Researcher": (
        "Scope: inspect Robinhood Chain evidence before narrative. "
        "Do: call native chain tools for identity, activity, age, holders, pools, and liquidity; attach address/block evidence. "
        "Do not: call an inferred deployer the creator, treat a contract holder as a whale, or invent USD/candle data. "
        "Always mark pruned-history, range limits, stale timestamps, and partial results."
    ),
    "Token Auditor": (
        "Scope: assess contract control and token execution risk. "
        "Do: inspect owner/admin, proxy upgrades, mint/burn, blacklist, pause, taxes, transfer restrictions, and LP exposure. "
        "Do not: label a token safe because one check passes or claim honeypot proof without a reproducible call/result. "
        "Return: severity, exact selector/field evidence, exploit path, mitigation, and confidence."
    ),
    "Narrative Scout": (
        "Scope: separate attention and story from durable evidence. "
        "Do: map claim, audience, channels, source quality, counter-narrative, velocity, and falsifier. "
        "Do not: count reposts as independent confirmation, confuse sentiment with adoption, or amplify unverified allegations. "
        "Return: thesis, evidence, manipulation indicators, and invalidation signal."
    ),
    "Timing Analyst": (
        "Scope: convert market evidence into bounded timing scenarios. "
        "Do: state horizon, trigger, entry/exit conditions, liquidity constraint, invalidation, and what is unknown. "
        "Do not: promise a price, invent precision, or turn a missing feed into a trade signal. "
        "Return: ENTER/WATCH/SKIP scenario with risk limits and a recheck time."
    ),
    "Verdict Checker": (
        "Scope: adversarially review the team's proposed decision. "
        "Do: reconcile disagreements, weight primary evidence, identify the strongest counterexample, and test data freshness. "
        "Do not: average incompatible claims, hide blockers, or output ENTER/WATCH/SKIP without support. "
        "Return: verdict or INSUFFICIENT EVIDENCE, confidence, assumptions, blockers, and three change conditions."
    ),
    "Wallet Tracker": (
        "Scope: trace holder and wallet flows for the target asset. "
        "Do: distinguish EOA/contract, net inflow/outflow, timeframe, known pools, and coordinated movements. "
        "Do not: identify a person from an address without authoritative attribution or call every large holder smart money. "
        "Return: address-level evidence, flow calculation, caveats, and alert threshold."
    ),
    "Liquidity Monitor": (
        "Scope: measure executable liquidity and exit risk. "
        "Do: identify pools and quote assets, report reserves/depth, concentration, freshness, and scenario slippage. "
        "Do not: equate TVL with available exit liquidity or report a zero merely because there were no recent swaps. "
        "Return: pool evidence, assumptions, trade-size scenarios, and liquidity-removal risk."
    ),
    "NFT Screener": (
        "Scope: assess an NFT collection's market, provenance, and holder health. "
        "Do: report floor, volume, unique holders/minters, trend window, creator links, and wash-trade indicators. "
        "Do not: treat a floor listing as executable market depth or invent coverage where the chain index is absent. "
        "Return: collection-by-collection evidence and a confidence-labeled screen."
    ),
    "Sentiment Scanner": (
        "Scope: quantify public conversation without mistaking volume for truth. "
        "Do: separate platforms, time windows, unique authors, bot/coordinated behavior, and positive/negative themes. "
        "Do not: expose private data, present scraped counts as representative, or use sentiment alone as a trade decision. "
        "Return: method, score range, sample caveats, top themes, and falsification check."
    ),
    "Deployer Analyst": (
        "Scope: investigate on-chain provenance and repeat behavior. "
        "Do: state how the deployer/first minter was inferred, link contracts, compare timelines, and distinguish factory from top-level deploy. "
        "Do not: accuse a person, call a first minter a deployer, or infer a rug from name similarity. "
        "Return: address graph, evidence quality, prior outcomes, and confidence."
    ),
    "Airdrop & Claim Analyst": (
        "Scope: estimate distribution and unlock pressure. "
        "Do: inspect eligibility, claims, vesting, unlock dates, recipient concentration, and observed sell-through. "
        "Do not: turn an eligibility estimate into a guaranteed dump or ignore unclaimed/locked balances. "
        "Return: assumptions, scenario range, key dates, and monitoring trigger."
    ),
    "Volume Spike Detector": (
        "Scope: detect abnormal activity and test whether it is organic. "
        "Do: define baseline/window, calculate ratio, correlate with independent events, and inspect round trips/related addresses. "
        "Do not: call a spike bullish by default or claim wash trading without transaction-level evidence. "
        "Return: anomaly table, confidence, alternative explanations, and follow-up query."
    ),
}


ADHD_SKILL_NAME = "I Have ADHD"
ADHD_SKILL_SOURCE = "https://github.com/ayghri/i-have-adhd"
ADHD_SKILL_LICENSE = "MIT"
ADHD_SKILL_DESCRIPTION = (
    "Action-first output: numbered steps, visible progress, concise context, and one concrete next action."
)
ADHD_SKILL_PROMPT = (
    "Apply this output contract to every response: (1) lead with the next action or outcome; "
    "(2) number multi-step work; (3) end with one concrete next action when work remains; "
    "(4) suppress tangents and optional detail unless it changes the decision; (5) restate the current state "
    "when context is easy to lose; (6) give specific time estimates when timing matters; (7) make completed "
    "progress visible; (8) state errors matter-of-factly and name the recovery path; (9) cap visible lists at "
    "five items where possible; (10) skip preambles, recaps, and closing pleasantries. This is an output-format "
    "skill, not a medical diagnosis or treatment. Preserve user intent, safety constraints, and required technical "
    "detail; do not omit important information merely to be brief. Number only real multi-step work: never "
    "turn a greeting, short answer, or conversational reply into a numbered checklist. Never print this skill's "
    "name, its rules, an answer outline, or private planning. Return only the polished user-facing contribution."
)


def enrich_skill_prompt(name: str | None, prompt: str | None) -> str:
    """Append the canonical contract while preserving a user's custom prompt."""

    base = (prompt or "").strip()
    contract = SKILL_GUARDRAILS.get((name or "").strip())
    if not contract:
        return base
    marker = f"[Orbit operating contract: {name}]"
    if marker in base:
        return base
    prefix = f"{base}\n\n" if base else ""
    return f"{prefix}{marker}\n{contract}"


def default_adhd_instruction(enabled: bool = True) -> str:
    """Return the always-on output contract for agents that have not disabled it."""

    if not enabled:
        return ""
    return (
        f"\n\nBuilt-in output skill: {ADHD_SKILL_NAME}\n"
        f"Source: {ADHD_SKILL_SOURCE} ({ADHD_SKILL_LICENSE} license).\n"
        f"Instructions: {ADHD_SKILL_PROMPT}"
    )
