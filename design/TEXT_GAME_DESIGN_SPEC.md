# Text Game Design Spec

Sources of truth:

- `design/concepts/text-game-desktop.png` — 1536×1024 desktop primary screen.
- `design/concepts/text-game-mobile.png` — 852×1848 mobile responsive flow.

The concepts provide layout and visual language. Real team marks, invented statistics, and unsupported extra abilities shown by image generation are explicitly excluded. All UI text, score, field state, ratings, controls, logs, and tables are code-native.

## Product surface

The complete M4 screen contains:

1. Slim header: `CPBL 數據野球`, model version, fixed seed, reset.
2. Score rail: away/home score, inning/half, outs, compact line score.
3. Live matchup: code-native base diamond, current batter and pitcher, Contact/Power/Eye and Stuff/Control/HR Suppression only.
4. Controls: `下一打席`, `模擬半局`, `模擬全場`, `重新開始`.
5. Chronological play log.
6. Away/home lineups and compact box-score summary.

No navigation sidebar, marketing hero, account, store, gacha, trading, Fielding, Arm, Movement, Clutch, Defense, or player portraits.

## Design tokens

- `--ink-950: #050b12` — true dark navy-black page background.
- `--ink-900: #09131d` — primary surface.
- `--ink-850: #0d1924` — raised/open panel.
- `--line: #263440` — borders and separators.
- `--text: #f4f2eb` — warm white primary text.
- `--muted: #94a0aa` — secondary text.
- `--red: #e63242` / `--red-deep: #a91624` — primary action and batting accent.
- `--amber: #f3b83f` — inning, occupied base, pitcher accent.
- `--field: #46643b` — restrained field fill.
- Radius 6/10/14px; panels use 1px borders and little/no shadow.
- Spacing scale 4/8/12/16/24/32px.
- Motion 160–220ms; respect reduced motion.

Typography: `Arial Narrow`, `Roboto Condensed`, `Noto Sans TC`, system sans fallback. Score numerals use condensed 700 weight with tabular figures; controls use deliberate 15–18px weights, never browser defaults.

## Layout

Desktop ≥1100px: 12-column shell. Score rail spans full width. Main live panel spans 8–9 columns; play log spans 3–4. Matchup panel uses batter / diamond / pitcher. Lineup tables and summary form a lower band. Controls remain a four-button row at the bottom of the live region.

Tablet 700–1099px: score remains full width; matchup becomes one column; play log follows; lineups horizontally scroll if needed.

Mobile <700px: compact header and score, batter/diamond/pitcher in one focal panel, primary button full prominence with two secondary actions, play log below, then lineup/score sections. No squeezed desktop sidebar. Touch targets are at least 44px.

## Component inventory

- `AppShell`, `GameHeader`, `ScoreRail`, `BaseDiamond`
- `PlayerMatchup`, `RatingMeter`
- `GameControls`, `PlayLog`
- `LineupTable`, `GameSummary`
- loading, API error, and final-game states

All repeated UI uses shared primitives/tokens. `App` is composition glue; network/session state lives in a dedicated hook/client.

## Interaction contract

- Initial load creates a fixed-seed game and renders state.
- `下一打席` advances exactly one PA and prepends/appends one log event.
- `模擬半局` advances until half/inning/final changes.
- `模擬全場` advances to final.
- `重新開始` resets to the selected seed.
- Buttons disable during mutation; API errors render visibly and accessibly.
- Finished game disables simulation controls except reset and clearly shows winner.

## Allowed first-viewport copy

`CPBL 數據野球`, `模型`, `種子`, `局`, `上`, `下`, `出局`, `打者`, `投手`, `Contact`, `Power`, `Eye`, `Stuff`, `Control`, `HR Supp.`, `下一打席`, `模擬半局`, `模擬全場`, `重新開始`, `攻防紀錄`, `客隊`, `主隊`.
