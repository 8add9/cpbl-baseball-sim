# Balance Model

## Fixed rating inputs

Batter `A_WinsorizedBalanced`: Contact, Power, Eye, SpeedProxy. SpeedProxy means steal tendency/baserunning proxy, not sprint speed.

Pitcher `B_Role`: Stuff, Control, HRSuppression, Stamina. Stuff is a strikeout-result proxy; HRSuppression is not Movement; Stamina is a workload/durability proxy.

Both use `B_QuadraticTanh` on the existing final score. No named-player bonuses are allowed.

## PA outcome contract

Initial supported outcomes: BB, HBP, SO, OUT, 1B, 2B, 3B, HR. Returned probabilities must be finite, within `[0,1]`, and sum to one.

The initial neutral environment is the PA-weighted 2021–2025 CPBL baseline with intentional walks removed (`NPA=123,146`): BB 7.5000%, HBP 1.3106%, SO 17.1333%, OUT 50.8316%, 1B 17.6035%, 2B 3.8540%, 3B 0.4296%, HR 1.3374%. Twelve residual PA are absorbed into OUT and audited. 2026 is excluded.

## Research candidates

1. Multinomial log-odds adjustment around league baseline.
2. Multiplicative outcome odds followed by normalization.
3. Hierarchical decomposition: free pass -> strikeout -> ball in play -> hit/out -> hit type.

The hierarchical candidate is accepted for v0.1 because it reduces unrelated cross-talk while preserving probability mass. Stage A is a BB/HBP/SO/contact softmax; later conditional stages choose HR, non-HR hit/out and hit type.

## Calibrated v0.1 coefficients

All inputs are final composite Scores, where RatingRaw 65 maps to Score 0. Batter slopes use 2,940 completed 1990–2025 PA>=50 seasons; pitcher slopes use 2,061 completed eligible SP/RP/Swingman seasons. Intentional walks are excluded.

```text
eta_BB  = log(p0_BB/p0_C)  + 0.318166 Eye     - 0.332053 Control
eta_HBP = log(p0_HBP/p0_C)                     - 0.183413 Control
eta_SO  = log(p0_SO/p0_C)  - 0.319508 Contact + 0.292498 Stuff
(BB,HBP,SO,C) = softmax(eta_BB,eta_HBP,eta_SO,0)
logit(HR|C)       = logit(p0_HR|C)       + 0.411641 Power - 0.381629 HRSuppression
logit(hit|nonHR C)= logit(p0_hit|nonHR C)+ 0.093072 Contact
logit(XBH|nonHR H)= logit(p0_XBH|nonHR H)+ 0.133431 Power
```

These are descriptive season-card coefficients, not independently identified batter-vs-pitcher causal interactions or future projections. Rating 100 is Score 4.9604, so the linear log-odds tail is intentionally flagged for a monotone saturating-tail comparison before game-balance freeze.

`65 vs 65 = selected league baseline` is a product anchoring convention. It does not assert that historical Score-0 players exactly equal the PA-weighted league rate. In the 2021-2025 environment, the Power 100 counterfactual reaches roughly 9.19% HR per PA; observed historical Score 4.5-5.5 seasons averaged lower across their actual era environments, so M3 must retain a saturating-tail sensitivity model.

The accepted version must document coefficients, baselines, bounds, interactions, and calibration evidence.

## Required sensitivity

- Power raises HR and extra-base damage with diminishing returns.
- Contact lowers SO and improves contact/hit outcomes without duplicating all Power value.
- Eye raises BB/free-pass outcomes.
- Stuff raises SO.
- Control lowers BB/free-pass outcomes.
- HRSuppression lowers HR.
- Stamina does not directly alter one-PA quality in v0.1; later fatigue models may consume it.

## Evidence policy

Use fixed seeds, at least 100,000 PA per golden matchup, effect sizes, confidence intervals where material, property tests over broad inputs, and versioned regression tolerances.
