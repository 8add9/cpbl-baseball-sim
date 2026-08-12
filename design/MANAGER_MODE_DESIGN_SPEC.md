# Manager Mode 1-2 Design Specification

## References

- Desktop: `design/concepts/manager-dashboard-desktop.png`
- Mobile: `design/concepts/manager-dashboard-mobile.png`
- Existing system reference: `design/concepts/career-dashboard-desktop.png`

The generated concepts define layout, density, typography character, panel anatomy,
color, and responsive hierarchy. Their illustrative names, teams, logos, dates, rarity
letters, and any `總值` column are not product data and must not be copied. The rendered
product uses only API data and supported Model A/B component ratings.

## Product contract

The first Manager release lets a user create/load a six-team league, inspect the
server-built 22-card roster, review lineup/bench/rotation/bullpen, see budget and tier
caps, view standings and the next scheduled game, and simulate the next game, next
schedule round, or remaining season. It does not expose trades, contracts, gacha,
ownership markets, injuries, Fielding, Arm, or a fabricated Overall.

The server remains authoritative for card identity, legality, results, revisions, and
saves. The browser displays RatingRaw-derived component values but never computes game
outcomes, tiers, costs, or standings.

## Desktop composition

Use a three-column console at 1440×900:

1. Catalog/roster identity rail: compact filters and player-season rows when catalog
   browsing is available; until manual roster editing ships, show the active team's
   roster summary and selected-card supported component ratings.
2. Primary roster region: budget, tier usage, exact nine-position lineup, four bench
   cards, four-SP rotation, and five-card bullpen.
3. League region: six-team standings, next scheduled matchup, and compact season status.

The command rail spans the lower viewport and contains exactly three primary simulation
actions plus recent results. Prefer tables and open rails over nested cards.

## Mobile composition

At 390×844 use one column with four text tabs: `陣容`, `球員目錄`, `戰績`, `賽程`.
The first release may keep `球員目錄` read-only. Budget and next matchup stay above the
tabs. The selected roster tab shows lineup first, then compact bench, bullpen, rotation,
and standings preview. Simulation controls remain reachable without horizontal overflow;
touch targets are at least 44px.

## Visual tokens

- Background: near-black navy, never cream or neutral gray.
- Panels: dark navy with thin steel-blue borders and minimal shadow.
- Primary: CPBL red for selected state and next-game action.
- Secondary emphasis: restrained amber/gold for budget and batch simulation.
- Positive: green only for saved status and wins.
- Type: condensed sports-display headings with readable sans-serif body/table text.
- Corners: small radius; no floating glass panels, pills, or mobile tile grid.

## Required states

- Initial loading and structured API error.
- League picker/create state.
- Active league with revision/autosave metadata.
- Busy state disabling mutations.
- Completed season disabling simulation actions.
- Desktop and mobile responsive states with no document overflow.

## Fidelity exceptions

- No CPBL/team trademarks or generated logos are shipped in Phase 1; use text team IDs.
- No player photos or raster UI elements are shipped; all controls and tables are
  code-native.
- Component ratings replace every illustrative `總值` in the generated references.
- 2026/incomplete cards remain excluded from competitive league creation.
