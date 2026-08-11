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

The hierarchical candidate is the leading design because it reduces unrelated cross-talk while preserving probability mass. It is not accepted until M2 candidate comparison and calibration evidence pass.

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
