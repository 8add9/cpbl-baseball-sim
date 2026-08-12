# CPBL Baseball Sim 開發交接

更新日期：2026-08-12

正式 repository：[8add9/cpbl-baseball-sim](https://github.com/8add9/cpbl-baseball-sim)

正式 Web：[GitHub Pages](https://8add9.github.io/cpbl-baseball-sim/)

## 1. 目前狀態

| 範圍 | 狀態 | 說明 |
|---|---|---|
| Rating research / export | 完成現行版本 | 打者 Model A、投手 Model B_Role，30–110 使用 B_QuadraticTanh；2026 標為未完季 |
| PA 機率模型 | 完成 v0.1 | 正式 hierarchical PA model；不以前端或第二套 RNG 抽結果 |
| 九局文字比賽 | 完成 v0.1 | immutable GameState、逐 PA、半局／全場模擬、延長、再現性 |
| Manager Mode | 完成現行 v0.1 範圍 | 陣容、棒次、輪值、真實隊名、120 場／隊、跨季、排名獎勵、球員數據、SQLite autosave |
| Career v3 | 可運作舊版 | 建角、成長、完整比賽、SQLite save；不是新版產品規格的完成版 |
| Career v4 | 本機 foundation、未正式上線 | 週曆、AP、疲勞、狀態、v4 aggregate/persistence/API 骨架；Web 與完整生涯循環仍待完成 |
| 全民打棒球／抽卡交易 | 未開始 | 依產品決策，Phase 1 完成後先暫停，不往此範圍擴張 |

## 2. 本次 Manager 球員數據功能

- 「球隊球員數據」只顯示 `user_team_id` 所屬球員。
- 「聯盟球員數據」顯示聯盟所有出賽球員，且每筆標示球隊名稱。
- canonical 統計仍只有一份；前端只是不同 scope，不重複保存資料。
- `PlayerSeasonStat` 的識別改為 `(team_id, card_id)`，季中換卡後原數據仍保留原球隊歸屬。
- API 統計列新增 `team_id`、`team_name`、`card_season_year`。
- 舊存檔會用當前 roster 補上可推導的球隊；真的無法推導的舊歷史列會顯示「歷史資料（球隊未記錄）」，不會錯歸到玩家球隊。

目前統計口徑：

- 打者：G、PA、AB、H、2B、3B、HR、BB、HBP、SO、AVG、OBP、SLG、OPS。
- 投手：G、GS、IP、BF、H、HR、BB、HBP、SO、R、RA9、WHIP。
- 投手的 R／RA9 目前是簡化口徑；engine 尚未保存 inherited runner 的 responsible pitcher。

## 3. 重要版本與資料

- Rating snapshot：`rating-snapshot-v0.2`
- Rating engine：`rating-engine-v0.1`
- Batter model：`A_WinsorizedBalanced-v0.1`
- Pitcher model：`B_Role-v0.1`
- PA model：`pa-hierarchical-v0.1`
- Game rules：`station-to-station-v0.1`
- Manager save：schema v2、`manager-sqlite-v1`
- Rating artifacts：`artifacts/generated/ratings/`
- 原始 SQL `BaseballRealData` 為唯讀來源，不得由遊戲功能 UPDATE／DELETE。

## 4. 執行與驗證

Python：

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m mypy src
```

Web：

```powershell
cd web
npm test -- --run
npm run lint
npm run build
```

部署拓樸：GitHub Pages 靜態 React → HTTPS tunnel → Linux loopback FastAPI → SQLite volume／唯讀 rating artifacts。後端不得直接公開 bind 到公網。

## 5. Career Mode 尚未完成

新版 Career Mode 不能再以「一直按下一打席」作產品主循環。主要待辦：

1. 把 Career v4 的週曆／AP／每日 action aggregate 正式接入 Web。
2. 完成 training、recovery、fatigue、form、injury、trust、team status 與實際出場決策的單一 authoritative 流程。
3. 將 Normal／Aggressive／Patient／Power／Contact／Situational approach 接入同一正式 PA engine，完成數值 Monte Carlo gates。
4. 完成 regular season → season review → awards → contract → offseason training → next season 狀態機。
5. 增加可信的聯盟 cohort，獎項必須由實際模擬統計排名產生，不能依 Rating 直接頒獎。
6. 補 R／RBI 的可稽核 runner attribution；SB／CS 在 runner-event model 完成前不可假裝支援。
7. 完成 v3 → v4 存檔 migration／封存策略與 production rollout。
8. 完成至少兩個完整球季的 desktop＋mobile browser E2E、restart/reload exact replay。
9. 執行 1,000 fictional players × 10 seasons balance validation；退休分布需另跑 lifespan cohort 至 45 歲。

## 6. 已知限制與風險

- 跑壘仍是 station-to-station provisional model；沒有完整 SF、DP、error、FC、WP、PB 與逐跑者責任資料。
- Fielding／Arm 尚未研究或進入比賽；SpeedProxy 尚未完整影響跑壘；不得把它們包裝成已完成能力。
- Manager 目前沒有交易、合約、農場、傷病、完整守備價值或真實多守位歷史。
- SQLite 是單一服務實例／本機 volume 契約，尚無 replication 或多人帳號隔離。
- 2026 為進行中資料，只能展示／exhibition，不應進競技校準。
- 公開使用 CPBL 衍生資料、姓名、隊名、商標與 Logo 仍需法務／授權審查。

## 7. Working tree 與發布注意

本次 Manager 變更與交接文件可以獨立發布。工作目錄另有 Career v4 未提交檔案，不能誤混入 Manager commit：

- `src/baseball_sim/api/app.py`
- `src/baseball_sim/api/career_v4_routes.py`
- `src/baseball_sim/api/career_v4_schemas.py`
- `src/baseball_sim/career/aggregate_v4.py`
- `src/baseball_sim/career/persistence_v4.py`
- `tests/api/test_career_v4_api.py`
- `tests/career/test_persistence_v4.py`

發布 Manager 時必須精確 stage 指定檔案，禁止 `git add -A`。下一位開發者應先決定 Career v4 這批檔案要獨立 commit、繼續開發或暫存，不要覆蓋。

## 8. 建議下一步

1. 完成本次 Manager stats 的 CI、Pages 與 Linux backend deployment 驗證。
2. 對文件做一次 reconciliation：更新過期的 in-memory Game 與舊測試數說明。
3. 以獨立 commit 接續 Career v4 aggregate，再做 Web weekly dashboard vertical slice。
4. Career v4 兩季 E2E 與 production restart 證據完成後，再判定 Phase 1 是否可正式封版。
