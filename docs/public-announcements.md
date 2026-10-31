# 公開公告維護手冊

本功能是「公開資料＋私人 Gmail」整合版。公開區免登入，私人郵件仍沿用 Google OAuth / 帳號隔離。
2026-11-01 正式產品版本 7c69350、schema 0009；本文補強首次正式執行8篇成功、0失敗。每小時公開同步已啟用，首次手動 Actions 驗收成功；當時132則、最後成功更新23:00。歷史階段文件保留當時未部署狀態，最新證據見[發布紀錄](release-2026-11-01.md)。

## 學生入口

首頁 `/` 以303直接導向 `/public/announcements`，保留查詢字串；可免登入搜尋、分類及篩選學生相關。學生相關是規則提示，不代表本人符合資格。裝置待辦在 `/todos`。

正式預設不掛載合成示範；`/demo` 及 `/demo/announcements/{demo_id}` 轉回公開清單。示範僅供內部測試明確 `demo_enabled=True` 啟用，不寫入公開資料庫。

Gmail 是選用的私人整合，仍有 Google 測試名單限制，不影響公開閱讀。管理者啟動 `app.web:app` 仍需既有資料庫、OAuth 與 Session 設定；單人 `app.main:app` 不能直接作為多人公開服務。

公開頁顯示官方來源、最後成功更新（台灣時間）、失敗／過期提示與收錄限制。來源更新失敗保留資料，超過2小時或尚無成功紀錄提醒；不是用頁面載入時間代替更新時間。搜尋無結果與尚無收錄資料分開提示。

## 行動資訊與修正保存

公開／私人／示範詳情使用同一行動卡介面。規則與原文支持才呈現確定日期，年份推定／跨年／範圍／角色衝突顯示待確認；截止與活動分欄。來源摘要可能截短；既有 AI 不作唯一依據，不啟用分析、擷取或新權限。

公開修正按儲存才寫入此裝置 IndexedDB（包括用來追溯的公開原文快照），不傳回伺服器，不隨帳號切換；共用瀏覽器可能看到，勿填入私人郵件。額度不足或分頁衝突不會回報成功。可重新讀取版本並保留輸入，來源版本改變時須再核對。清除裝置修正歷史不可還原，但不影響公開公告。

私人修正與原快照存於本人帳號，不進 browser storage；重新解析公告不刪除原快照，帳號刪除會一併刪除本人新資料，備份限制沿用隱私說明。示範修正只用頁面記憶體，重載清空。第三階段另提供明確加入的待辦，第四階段提供確認後下載ICS，第五階段提供保留各來源原文的可靠網址關聯，不實體合併。

詳見 [第二階段驗證](campus-action-phase2-validation-2026-10-29.md)。

## 收錄範圍

- 指定清單：https://www.nkust.edu.tw/p/422-1000-1001.php 。
- 官方 RSS：https://www.nkust.edu.tw/p/503-1000-1001.php 。實查回傳 20 則近期公告，不代表歷史全量。
- 全部收錄指定來源取得的公告。學生相關、分類不影響收錄，未知公告仍保存在「全部」。
- 摘要只來自來源提供的文字，可能截短；未提供發布時間時顯示未知，不用抓取日猜日期。
- 既有可靠官方文章由排程分批讀取本文；每批8篇、最新200則範圍，不抓附件或外部報名頁，也不使用AI。失敗保留摘要與舊本文，不保證涵蓋全校或所有Gmail通知。

## 安裝與資料庫

多人網站仍由 `app.web:app` 啟動，使用 `requirements-web.txt`，新增 `defusedxml==0.7.1`。
執行開發測試則安裝 `requirements-dev.txt`；鎖定環境使用 `requirements-lock.txt` 時也需有 defusedxml。

本分支 migration head 是 **0009**；0006 是公開公告版本，0007 新增私人修正快照／歷史表，0008 新增私人待辦，0009 新增公開與私人隔離的來源版本表。10/31 正式發布已通過 schema 0009 gate；本次入口／排程補修沒有新增 migration。請先依 Phase 9 手冊備份資料庫與金鑰，再在確認的目的多人庫執行：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

0006 只新增獨立公開公告、來源狀態與維護紀錄表。現有私人表的帳號約束不變。
CLI 不自動遷移；錯誤 `PUBLIC_MIGRATION_REQUIRED` 表示需由維護者確認 migration。
不要把舊單人 SQLite 當成多人資料庫。啟動腳本會先 migration，再執行新版 preflight。

## 日常更新

在專案根目錄，使用已設定的多人 `DATABASE_URL` 執行；不需要 Gmail 或 AI 金鑰：

```powershell
.\.venv\Scripts\python.exe -m app.public_cli sync --source nkust-latest
```

成功 stdout JSON 包含 added / updated / unchanged / failed / status；exit 0 表示成功。
來源或資料部分失敗為 exit 1，參數錯誤為 exit 2。來源失敗保留上次資料。
同一來源的同步 / 補收 / 重分類共用資料庫 lease；`PUBLIC_SYNC_BUSY` 表示請稍後再試。
lease 最長 10 分鐘，程序中斷後可在到期後重試。不要手動清除仍在執行中的 lease。

正式排程位於 main 的 `.github/workflows/public-announcements.yml`，每小時17分（UTC，台灣時間的分鐘相同）嘗試執行，checkout `codex/web-deployment`，不依賴 Render 休眠狀態。不提供匿名「立即更新」端點。

專用 `nkust_public_sync` 角色只讀寫公開公告、狀態、同步紀錄與公開版本及必要序列，讀 schema version；無私人表讀取、DELETE、CREATE 或管理角色權限。grants 見 `scripts/sql/public_sync_grants.sql`，密碼由管理者親自設定，連線只存 `NKUST_PUBLIC_SYNC_DATABASE_URL` Actions Secret。不要用 Neon Roles UI 建立此角色（其預設繼承過大權限）。不要把管理員、Gmail、OAuth 或 Session 憑證加入工作流程。

手動重試：到 GitHub Actions → Update public announcements → Run workflow（main）。檢查 sync 狀態與 JSON 計數，成功後比對網站最後成功更新。憑證到期或失效時由管理者輪替專用角色密碼並更新同名 Secret，不擴大角色權限；不要把密碼放進 issue／聊天／Git。單次執行上限10分鐘，併發序列化，另有既有資料庫lease保護。

GitHub 排程可能延後，公開repo60天無活動可能自動停用；必要時由管理者在 Actions 重新啟用。Render 免費網站首次開啟仍可能需要喚醒。RSS僅近期20則，不等於全歷史。首次手動成功不能當作下一小時排程已驗收。

## 官方本文分批更新

同一個Actions同步步驟在RSS成功後執行 `python -m app.public_cli articles --limit 8`。管理者可手動執行相同命令（limit允許1–20）；仍使用受限公開角色，不需額外權限。CLI的updated表示成功讀取篇數，不代表每篇官方內容有變。失敗回傳partial與exit1，可在Actions檢查；頁面保留之前本文並提示，尚未讀取則維持摘要。

本文保存在現有公開版本JSON，保留RSS；成功讀取時間與清單同步時間分開。RSS改變、本文尚未重讀時舊資訊標待核對；不會覆蓋已加入待辦的快照。日期衝突保留雙方依據，系統缺漏不等於沒有規定。詳見[本文補強說明](public-article-enrichment-2026-10-31.md)。

## 歷史補收

先執行近期 RSS 同步，再分批讀取歷史清單：

```powershell
.\.venv\Scripts\python.exe -m app.public_cli backfill --source nkust-latest --max-pages 5
```

每次預設 5 頁，允許 1–20 頁；請求至少間隔 2 秒，單批最多約 120 秒。
一次批次成功不表示全部歷史完成。重跑相同指令會從已提交游標繼續，直到驗證到合法末頁。
請先查看來源是否允許自動讀取；本次 robots 內容為 `User-agent: * / Allow: /`，不是全文再利用授權。
目前只保存標題、日期、來源摘要與連結，尚未批次抓取所有歷史原文。

狀態說明：

| 狀態 | 意義 |
| --- | --- |
| not_started | 尚未執行歷史補收 |
| incomplete | 已開始但未到合法末頁，或來源暫時無法讀取 |
| complete | 已完成一次歷史掃描，來源變動仍可能造成缺漏 |

游標僅在該頁交易成功後前進。遇到重複頁、頁碼不符、非公告 HTML、空頁或不允許的 URL，
停止並保留該頁游標；修復來源合約後重試，不把錯誤頁視為末頁。
清單 URL 與 RSS URL 有時指向不同的同主題頁面，第一版保守保留兩筆，不能僅因標題相同而合併。
不同 URL 保留查詢參數語意；RSS 不再出現某則公告不會觸發刪除。

## 重分類與網站操作

規則更新後可離線重算公開公告，不下載來源：

```powershell
.\.venv\Scripts\python.exe -m app.public_cli reclassify --source nkust-latest
```

`/` 直接導向免登入公開清單，`/public/announcements` 為公開清單，`/public/announcements/{id}` 為詳情。
對象預設全部；學生相關是規則提示，不是資格判斷。搜尋與分類可組合，清除篩選回到全部。
`/announcements` 仍是私人郵件公告，未登入不能閱讀。公開路由不解析 cookie、也不回退到私人表。
刪除自己的帳號不會刪除公開公告。PWA 沒有新增離線公告快取。

## 驗證與發布

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
git diff --check
```

PostgreSQL 實機案例需使用獨立測試庫的 `NKUST_TEST_POSTGRES_URL`；不得沿用正式 DATABASE_URL。
SQLite 測試或 PostgreSQL 離線編譯不代表正式 Neon 已驗收。
發布前仍需核對備份、migration、公開頁匿名存取與私人帳號隔離；Google 私人 Gmail 功能的發布限制不變。

## 我的待辦

公開詳情的待辦只保存在裝置 IndexedDB v2，保留 v1 修正資料；/todos 查看，須自行加入才建立。私人待辦在 /my/todos，依帳號隔離，不匯入裝置待辦；示範只用記憶體。稍後到明天09:00台灣時間，顯示確切日期，到期重開頁或每分鐘檢查重新出現，不發推播。待辦保留加入時來源快照，來源變更需自行核對。移除保留內部版本墓碑，防止舊分頁重新覆寫；不刪公告／修正。詳見第三階段驗證紀錄。

## 行事曆檔案

公告詳情及待辦可分別選活動或截止，核對日期、來源及時間後下載.ics。pending/stale日期先回詳情確認修正，AI不作唯一依據；無時間可確認為全天，定時以Asia/Taipei核對後存UTC，結束可不填，不猜持續長度。待辦以加入時快照匯出。原文含未解析時間須自行選擇方式／核對後填寫，修改選項或修正資料後須重新確認。

瀏覽器本機產生，不新增上傳／下載HTTP路由或DB欄位；不改待辦完成狀態、OAuth、行事曆授權或schema。啟動下載不代表落盤或已加入行事曆；重複匯入結果由行事曆軟體決定。私人檔案含私人資訊且為純文字，需自行保護與匯入。驗證結果見第四階段紀錄。

## 來源關聯與留存

匿名 `/public/announcements/{id}/history` 只讀公開資料。本人 `/announcements/{id}/sources` 依可靠的 NKUST HTTPS 404/405/406 文章網址精確關聯公開與自己目前的郵件公告；保留path/query與host差異，僅移除fragment，不採用標題相似度或不可信GUID。相同網址不代表內容、期限、資格相同，請分別核對原文。

`/my/source-history` 每頁20筆，舊公告ID失效後仍可找本人已留存版本；詳細版保留原文、HTML（跳脫為文字）、原解析與來源日期。比較同郵件可靠文章URL前一版本；無可靠URL只比較相同原位置／指紋，不將重新排序的不同公告誤認更新。版本時間是服務觀察時間，解析器改版不一定是官方更新。首次留存前不回填虛構歷史。

在既有public/User同步lease交易內，先留舊版本再更新及留新版本；只省略相鄰相同快照，A→B→A仍留下三份。任何留存寫入失敗會回復整次交易。GET不寫入、不同步，來源讀取失敗顯示503而非空清單。私人資料不放入公開版本表或裝置儲存。刪帳號沿owner/email CASCADE清除本人版本，不動公開或其他帳號，備份清除限制沿原政策。版本紀錄會隨內容變更成長，尚未設定自動刪除。

正式schema 0009已於10/31發布，最新入口／排程補修通過575項獨立PostgreSQL測試；私人正式流程與容量限制仍見發布紀錄。
