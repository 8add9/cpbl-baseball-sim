# Game State Validation v0.1

## Result

All 1,000 fixed-seed neutral games reached a legal final state. Mean PA was 81.85; extra-inning rate was 15.30%; the longest game ended in inning 24.

## Scope

This validates deterministic state transitions, full-game termination, lineup cycling, counter-based replay, and regulation/extra-inning endings. It does not validate real CPBL runs per game. Station-to-station advancement omits sacrifice flies, double plays, errors, fielder's choices, runner speed, arms, and situational advancement, so run-environment calibration remains a later gate.
