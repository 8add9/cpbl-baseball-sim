# CPBL Baseball Sim 開發交接

更新日期：2026-08-15

正式 repository：[8add9/cpbl-baseball-sim](https://github.com/8add9/cpbl-baseball-sim)

正式 Web：[GitHub Pages](https://8add9.github.io/cpbl-baseball-sim/)

## 1. 目前狀態

| 範圍 | 狀態 | 說明 |
|---|---|---|
| Rating research / export | 完成現行版本 | 打者 Model A、投手 Model B_Role，30–110 使用 B_QuadraticTanh；2026 標為未完季 |
| PA 機率模型 | 完成 v0.1 | 正式 hierarchical PA model；不以前端或第二套 RNG 抽結果 |
| 九局文字比賽 | 完成 v0.1 | immutable GameState、逐 PA、半局／全場模擬、延長、再現性 |
| Manager Mode | 完成現行 v0.1 範圍 | 陣容、棒次、輪值、真實隊名、120 場／隊、跨季、排名獎勵、球員數據、SQLite autosave |
| Career v3 | migration-only | 舊 API 保留供既有邊界存檔轉入，Web 不再使用 |
| Career v4 | 完成 Phase 1 文字產品範圍 | 週曆、AP、訓練 XP、疲勞、整週／整季、季末、獎項、合約、休季、下一季、SQLite autosave |
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
- 投手：G、GS、W、L、IP、BF、H、HR、BB、HBP、SO、R、RA9、WHIP。
- 投手勝敗以「最終勝隊取得永久領先時的投手責任」作 deterministic 簡化判定，並非完整官方勝投資格規則。
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

## 5. Career Mode 現況

新版 Career Mode 已移除「一直按下一打席」主循環。目前入口是球員儀表板，
每週安排非比賽日訓練或恢復，再選擇逐日、整週或整季模擬。完成 120 場後，
必須依序通過球季總結、年度評價、合約、休季訓練，才能進入下一季。

已驗證：建立 v4 存檔、安排週計畫、完整模擬兩個 120 場球季、五段休季流程、
跨季生涯累計、每次 mutation revision/idempotency、SQLite 重啟後完全相同。

後續研究項目（不阻擋 Phase 1 文字版交付）：

1. Normal／Aggressive／Patient／Power／Contact／Situational 的逐打席選擇 UI。
2. 更完整的傷病、球隊 depth、先發／板凳／代打出場決策與聯盟 cohort 獎項排名。
3. R／RBI 逐跑者歸屬與 SB／CS runner-event model。
4. 1,000 人 × 10 季長期平衡與 35–45 歲退休分布研究。

## 6. 已知限制與風險

- 跑壘仍是 station-to-station provisional model；沒有完整 SF、DP、error、FC、WP、PB 與逐跑者責任資料。
- Fielding／Arm 尚未研究或進入比賽；SpeedProxy 尚未完整影響跑壘；不得把它們包裝成已完成能力。
- Manager 目前沒有交易、合約、農場、傷病、完整守備價值或真實多守位歷史。
- SQLite 是單一服務實例／本機 volume 契約，尚無 replication 或多人帳號隔離。
- 2026 為進行中資料，只能展示／exhibition，不應進競技校準。
- 公開使用 CPBL 衍生資料、姓名、隊名、商標與 Logo 仍需法務／授權審查。

## 7. 首頁與發布

- Web 首頁直接進入 Manager Mode；獨立的普通文字比賽畫面已從 App 移除。
- Manager 頁首可切換 Career Mode，Career 可返回 Manager。
- GitHub Pages 只部署靜態 Web；所有 Manager/Career mutation 仍由 Linux FastAPI
  與 SQLite 權威處理。

## 8. 建議下一步

依產品決策先暫停，不進入全民打棒球／抽卡交易內容。下一輪若繼續，優先順序是
Career 的逐打席策略、出場身分與 runner stats，而不是新增另一套遊戲系統。
