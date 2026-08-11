# Testing Strategy

## Test layers

- Unit: rating mapping, odds transforms, probability decomposition, base advancement, scoring, progression costs.
- Property: finite/bounded/sum-to-one probabilities, monotonic rating effects, legal state transitions, save round-trips.
- Golden matchup: versioned fixed archetypes and selected historical cards with fixed seeds.
- Monte Carlo: at least 100,000 PA per core comparison; larger samples for rare outcomes.
- Integration: read-only rating source, API/domain contracts, persistence, deterministic replay.
- Browser: real Text Game, Career, and Manager workflows.

## Initial golden grid

Vary one rating at a time through 50, 65, 80, 95, 105 for Contact, Power, Eye, Stuff, Control, and HRSuppression. Hold all other values at65. Assert expected monotonic outcomes and minimum meaningful effect sizes after empirical calibration.

## Required interaction fixtures

- High Power + low Contact
- High Contact + low Power
- High Eye + low Contact
- High Stuff + poor Control
- Low Stuff + elite Control
- Elite Stuff + elite Contact
- Elite Power + elite HRSuppression

## Reproducibility

Every simulation entry point accepts a seed. Tests compare deterministic counts for a fixed engine version and statistical bands for cross-version balance behavior.

## Milestone rule

A green build is insufficient. Each milestone requires its acceptance tests, actual execution, QA evidence, bug fixes, and current documentation.
