---
name: baseball-simulation-balance
description: Validate CPBL baseball rating, batter-pitcher simulation, probability, progression, and card-balance changes. Use whenever modifying player ratings, score-to-rating mappings, plate-appearance outcome formulas, matchup interactions, player development, card tiers, roster constraints, or any probabilistic baseball gameplay rule.
---

# Baseball Simulation Balance

Treat balance as an evidence-backed regression problem. Never tune a named player by exception.

## Required workflow

1. Identify every rating and probability affected by the change.
2. Preserve immutable historical source data; write derived data outside `BaseballRealData` raw tables.
3. State the league baseline, mathematical transform, bounds, and expected direction before editing.
4. Add or update deterministic unit, property, golden-matchup, and Monte Carlo regression tests.
5. Run one-variable sensitivity at ratings 50, 65, 80, 95, and 105.
6. Run interaction cases relevant to the change.
7. Use fixed seeds and large samples; never judge balance from one game.
8. Report effect size, uncertainty, and baseball sanity, not merely that two outputs differ.
9. Update `BALANCE_MODEL.md`, `DECISIONS.md`, `TESTING.md`, and `KNOWN_ISSUES.md` when behavior or evidence changes.

## Non-negotiable gates

- Every relevant rating must materially affect at least one intended outcome in the correct direction.
- Higher Power must not reduce HR rate or SLG when other inputs and seed policy are controlled.
- Higher Contact must not increase strikeout rate under the same matchup.
- Higher Eye must not reduce walk rate.
- Higher Stuff must not reduce pitcher strikeout rate.
- Higher Control must not increase free-pass rate.
- Higher HRSuppression must not increase HR rate.
- Probabilities must be finite, lie in `[0, 1]`, and sum to one within numerical tolerance.
- Diminishing returns and explicit bounds must prevent runaway outcomes.
- Simulation and ranking must use raw scores/ratings, never rounded display values.
- Important probabilistic functions require property tests over broad valid input ranges.

## Golden regression policy

Keep permanent fixtures for ordinary, star, and extreme archetypes plus named historical cards selected only as regression labels. For each core formula change:

- Run at least 100,000 PA per golden matchup; use 1,000,000 when tail rates or close comparisons require it.
- Record PA, AVG, OBP, SLG, OPS, K%, BB%, HR%, 1B%, 2B%, and 3B%.
- Compare effect sizes and confidence intervals with versioned tolerances.
- Fail on monotonicity reversal, invalid probability, unexplained large drift, or loss of seed reproducibility.

## Interaction matrix

At minimum test high Power + low Contact, high Contact + low Power, high Eye + low Contact, high Stuff + poor Control, low Stuff + elite Control, elite Stuff + elite Contact, and elite Power + elite HRSuppression.

## Prohibited shortcuts

- Do not make ratings cosmetic.
- Do not hardcode bonuses for famous players or force stars to cross a display threshold.
- Do not use wins, saves, card tier, or player name as hidden skill inputs.
- Do not use an LLM to decide runtime outcomes.
- Do not accept a build-only check as balance QA.
- Do not change formulas merely to make a small simulated sample look plausible.
