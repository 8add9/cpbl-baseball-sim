# Career Mode 1-1 design specification

Reference concept: `design/concepts/career-dashboard-desktop.png`.

## Product boundary

Career Mode 1-1 follows one created batter from age 18. It supports Contact, Power,
Eye, and a read-only SpeedProxy. SpeedProxy cannot consume development points or affect
the plate-appearance model until a runner model is researched. The screen must not imply
Fielding, Arm, pitching careers, contracts, card ownership, or Manager Mode systems.

## Layout

- Keep the Text Game dark navy scorebook shell, CPBL red primary action, amber
  progression accent, and green only for field/baseball context.
- Desktop uses three information columns: player/archetype, development, and
  season/career statistics. Simulation controls and recent results form the lower rail.
- Mobile collapses to identity, progression, statistics, then controls. Creation and
  training actions remain reachable without horizontal scrolling.
- Use tabular numerals for ratings, costs, XP, and batting lines. Rating bars represent
  the open 30-110 scale; gameplay and ranking continue to use full-precision Raw values.

## Required states

- Career list and create form with numeric archetype preview, position, bats, and throws.
- Career dashboard with age, season, games, XP, development-point bank, autosave
  revision, and last saved time.
- Three active development rows with Score-derived Raw/Display rating, next purchase
  cost, potential limit, and a one-step train action; SpeedProxy is read-only.
- Season and career counting/rate statistics. Slash lines are labelled simplified while
  the PA model lacks sacrifice outcomes.
- Next plate appearance, quick game, simulate week, and simulate to next important event
  controls. The active-game view exposes the real M3 inning, outs, bases, score, and the
  created batter's results. Next event stops at a DP threshold, game end, or season
  boundary; month/season controls may remain secondary shortcuts.
- Clear retired, season-complete, busy, stale-revision, corrupt-save, and offline states.

## Interaction rules

- Every mutation sends the expected revision and an idempotency operation id.
- The server is authoritative for XP, development points, ratings, stats, and outcomes.
- Training previews never mutate local authoritative values. Overspend and potential
  violations return structured errors without partial state changes.
- Autosave success is visible but quiet; failure remains visible until resolved.
- Integer display ties never determine ordering or simulation.

## Concept fidelity ledger

The concept defines hierarchy, spacing, palette, and control grouping. Implementation
must replace decorative or unsupported details with actual domain data. In particular,
the concept's position/height/weight, standings, opponent identities, wins/losses, and
large multi-point training buttons are non-binding until their systems exist.
