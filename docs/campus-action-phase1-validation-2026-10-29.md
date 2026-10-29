# 校園通知待辦助手第一階段驗證

日期：2026-10-29。執行方式：使用者核准在本對話逐項實作。未推送、未部署，不操作正式資料庫／OAuth。

## 基線

基準 HEAD：7465a85。原工作區既有未提交 Dashboard、字型與 readiness 修改保留，不屬本階段。

原生工具建立 `campus-action-phase1` 工作區，但 sandbox 拒絕寫入；依工作區技能 fallback 在原功能分支目錄執行。原生工具不允許封存該工作區（primary checkout）；未使用、未修改其中程式。

pytest 首次收集 24 項成功。建立 `data/audit-cache` 後，獨立 SQLite 來源同步案例 1 passed。TestClient 在 sandbox 內仍停滯；`-o faulthandler_timeout=20` 顯示 Windows asyncio 建立 event loop 時停於 `socket._fallback_socketpair` 的 `accept`，尚未進入應用 lifespan。不是 SQL 或來源同步失敗。

透過自動審核允許，在 sandbox 外執行相同測試，不改 fixture 或產品安全設定：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_public_pages.py tests/test_public_sync.py tests/test_date_parser.py tests/test_user_isolation.py -q -p no:cacheprovider --basetemp=data/audit-cache/phase1-baseline-unsandboxed --tb=short -o faulthandler_timeout=20
```

結果：**24 passed，2 warnings，2.95 秒，exit 0**。警告來自 Starlette/httpx 與 anyio 棄用介面。

後續每輪使用全新 basetemp，避免清除既有測試資料。資料庫為 fixture 產生的臨時 SQLite，Google 為 FakeGoogle；沒有實際 Gmail／AI 或正式資料庫存取。

## 功能與最終驗收

| 項目 | RED → GREEN 證據 |
| --- | --- |
| 公開來源／空白狀態 | 新增 4 項測試先失敗；修改後公開頁＋同步＋私人公告驗證 29 passed，2 warnings，4.14 秒 |
| 獨立合成示範 | 新增 5 項測試先失敗（缺路由／模組）；示範＋公開頁＋Session＋PWA 共 35 passed，2 warnings，10.96 秒 |
| 載入／錯誤提示 | 新增錯誤及表單驗證 12 failed、1 passed；Node 先因缺少 submit 回饋失敗；修改後相關 pytest 64 passed，2 warnings，7.37 秒，Node exit 0 |
| 完整回歸 | 首輪 439 passed、37 skipped、2 warnings，42.27 秒；補齊有效 Cookie 後最終輪同樣 439 passed、37 skipped、2 warnings，67.15 秒，exit 0 |

完整回歸命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=data/audit-cache/phase1-review-final --tb=short -o faulthandler_timeout=30
node tests/announcement_filter_check.cjs
node tests/pwa_worker_check.cjs
git diff --check
```

pytest、兩項 Node 檢查及最終 diff 檢查均 exit 0。37 項 skipped 為未設定專用 PostgreSQL 連線的實機測試；SQLite／離線 SQL 編譯不能替代 PostgreSQL 實測。沒有 migration、套件依賴或 OAuth 設定變更。

## 實際瀏覽器驗收

以僅綁定 `127.0.0.1:8765` 的暫時預覽執行新版 `create_app`；使用全新臨時 SQLite、FakeGoogle、假 OAuth／Session 設定。公開詳情的長標題、來源失敗狀態亦為合成資料，未匯入或讀取正式資料。預覽不包含使用者 Gmail。

- 320px：首頁、公開清單、長標題詳情、示範清單 document scrollWidth 均不超過 innerWidth。
- 390px：長標題詳情與示範清單實際截圖核對，公告標題換行、來源與失敗提示可閱讀。
- 實際示範搜尋 Enter 後由三則變為一則；公開分類選擇後自動 GET，保留分類。
- 返回上一頁後 `aria-busy` 清除、載入訊息 hidden；Tab 可由搜尋至分類、由分類至清除，焦點 outline 為 solid。
- 無 JavaScript 的 GET／noscript 由 HTML 測試驗證，未另開停用 JavaScript 的瀏覽器環境。未實測手機實體裝置、最大系統字級或螢幕閱讀器。

截圖：本聊天視覺產物目錄的 `phase1-demo-mobile.jpg`（全頁）與 `phase1-demo-controls-mobile.jpg`（提示／表單），僅含合成示範資料。

## 階段界線與後續

第一階段不含行動資訊卡、使用者衍生資訊修正、待辦保存、ICS 或跨來源合併；系統的可行動提示仍不是使用者待辦。下一階段需以既有日期證據與分析結果設計行動卡，公開來源摘要不足時顯示待確認。

獨立最終審查使用全新上下文，檢視 `7465a85..3fbe05a` 所有產品程式與測試，結論：無 Critical／Important，可整合；兩項非阻擋建議為重試連結遺失上下文及公開頁未直接驗證有效 Cookie。後者屬計畫既有驗收要求，已補齊有效、偽造、匿名三種 Cookie 的公開頁隔離驗證，沒有修改產品行為，完整測試仍通過。不是新產品缺陷修復，不宣稱此次測試補強有產品 RED→GREEN。

**保留的小問題：**錯誤頁「重新載入」返回未篩選清單，不保留原詳情或搜尋條件。手動輸入超出範圍的正整數頁碼也沿用原有空頁行為。兩者不影響資料保存或帳號隔離。

所有本機提交均未推送，正式網站現況未於本次重新驗證。

## 執行裁定與代價

1. 原生工作區寫入受 sandbox 限制，先在原功能分支精確指定檔案提交，保留既有修改；代價是工作中依賴檔案範圍控管，非實體隔離。原生工作區是聊天主工作區，工具拒絕封存；交付時只將最終已提交版本同步至該乾淨工作區，供後續對話使用，不複製私人設定。
2. Bash helper 未在 PATH，使用同格式、同計畫專屬的 PowerShell ledger 記錄；代價是人工核對任務狀態。有效 Cookie 測試屬已核准驗收，補齊而不當作可忽略的文字修飾；代價是再跑一次完整測試。
3. 審查不涵蓋既有 Dashboard／字型／readiness 修改，代價是此次結論不能替它們背書。正式環境、OAuth、PostgreSQL、實體手機及螢幕閱讀器不在本次已驗證範圍；代價是本機結果不能替代這些環境的驗收。
4. 行動卡、待辦、ICS、合併維持分階段設計；代價是完整行動流程尚待第二、三階段。保留繼承的大頁碼空頁行為，代價是手動輸入極大頁碼可能看不到結果。唯一延期的審查小問題是重試遺失上下文，代價是使用者需重新輸入條件。
