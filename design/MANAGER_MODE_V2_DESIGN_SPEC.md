# Manager Mode v2 Design Specification

Reference concept: `design/concepts/manager-v2-dashboard-desktop.png`.

Manager v2 is a multi-season numerical front-office dashboard. The primary task is
editing a batting order and starting rotation, not opening cards or managing fatigue.

## Primary screen

- Top navigation: 經理首頁、陣容設定、球員數據、聯盟戰績、歷史紀錄.
- Header: editable user-team name, season number, W/L, Cost limit and SSR limit.
- Left rail: six-team standings using 中信兄弟、統一7-ELEVEn獅、樂天桃猿、
  富邦悍將、味全龍、台鋼雄鷹; next-game command below.
- Center: nine-row batting-order editor with reorder controls and exact starting
  defensive positions. A four-slot rotation editor may select the same SP repeatedly;
  Manager v2 has no fatigue/rest rule.
- Bench: the roster is extensible and supports at least ten bench batters. Bench
  composition has no position quota; ten catchers are valid. Every card still consumes
  Cost/SSR entitlement unless the exact team name is `8add9`. Exact-position checks
  apply only to the starting nine.
- Right rail: selected player current-season batting or pitching statistics, plus a
  versioned season-reward preview.
- Completed season: replace simulation commands with `進入下一個賽季` and an explicit
  reward summary. Starting a season is a server-authoritative, idempotent mutation.

## Reward policy v1

- First place: `+5 Cost limit`, `+1 SSR limit`.
- A team finishing last in two consecutive seasons receives the comeback reward in the
  second season: `+10 Cost limit`, `+2 SSR limit`.
- Other finishing positions receive no cap increase in v1.
- Grants accumulate permanently in a per-team entitlement ledger; a later non-winning
  season never removes an earlier increase.
- Rewards settle exactly once and are stored in season history. They alter future roster
  legality only; they never rewrite ratings or completed results.

## Special name policy

The exact, case-sensitive display name `8add9` has unlimited Cost and SSR caps. The
server exposes both as `null`/infinity and skips only those two cap checks. Renaming the
team restores its accumulated ordinary limits. If the current roster then exceeds them,
simulation and next-season start are blocked until the manager makes it legal; cards are
never removed automatically.

## Responsive behavior

Desktop target is 1440x900. At 390x844, navigation becomes tabs and the order editor,
rotation, stats and standings become separate views; reordering must remain keyboard and
touch accessible. Preserve the existing near-black/navy, CPBL red and restrained gold
system. Do not introduce gacha, packs, trades, 3D, player photography or Phase 2 systems.
