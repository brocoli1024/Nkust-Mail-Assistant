# 公開公告維護手冊

本功能是「公開資料＋私人 Gmail」整合版。公開區免登入，私人郵件仍沿用 Google OAuth / 帳號隔離。
10/28 工作區發布紀錄記載曾部署公開公告版；本次新增功能未部署，亦未重新確認今天正式環境的版本與收錄數。請區分本分支可執行的功能、歷史發布紀錄與正式環境現況。

## 學生入口與合成示範

首頁 `/` 提供「瀏覽公開公告」及「體驗合成示範」。公開清單 `/public/announcements` 可免登入搜尋、分類及篩選學生相關；學生相關是規則提示，不代表本人符合資格。

`/demo` 及 `/demo/announcements/{demo_id}` 使用獨立的三則合成資料；每頁明示非高科大真實公告，日期固定、不代表仍可報名。示範支援搜尋與分類，不讀取資料庫或私人 Session、不呼叫 Gmail、AI 或來源擷取，也不匯入資料庫。來源與真實收錄狀態只出現在公開頁，不套用到合成資料。示範不是「已加入待辦」的模擬，第一階段沒有待辦保存功能。

Gmail 是選用的私人整合，需登入與唯讀授權，目前仍有 Google 測試名單限制；不影響公開閱讀與示範。管理者啟動 `app.web:app` 仍需既有資料庫、OAuth 與 Session 設定。單人入口 `app.main:app` 不提供這套多人公開／示範路由，不能直接公開部署。

公開首頁、清單、詳情均顯示來源、最後成功更新（台灣時間）、失敗提示與收錄限制；歷史補收詳情可展開。讀取失敗時有繁中錯誤頁與重試入口，來源更新失敗則繼續顯示已收錄資料；不要以頁面載入時間替代成功更新時間。搜尋無結果與尚無收錄資料分開提示。

此階段沒有新增 migration、依賴或自動更新排程。驗證結果與限制見 [第一階段驗證紀錄](campus-action-phase1-validation-2026-10-29.md)。

## 行動資訊與修正保存

公開／私人／示範詳情使用同一行動卡介面。規則與原文支持才呈現確定日期，年份推定／跨年／範圍／角色衝突顯示待確認；截止與活動分欄。來源摘要可能截短；既有 AI 不作唯一依據，不啟用分析、擷取或新權限。

公開修正按儲存才寫入此裝置 IndexedDB（包括用來追溯的公開原文快照），不傳回伺服器，不隨帳號切換；共用瀏覽器可能看到，勿填入私人郵件。額度不足或分頁衝突不會回報成功。可重新讀取版本並保留輸入，來源版本改變時須再核對。清除裝置修正歷史不可還原，但不影響公開公告。

私人修正與原快照存於本人帳號，不進 browser storage；重新解析公告不刪除原快照，帳號刪除會一併刪除本人新資料，備份限制沿用隱私說明。示範修正只用頁面記憶體，重載清空。沒有待辦、ICS 或跨來源合併。

詳見 [第二階段驗證](campus-action-phase2-validation-2026-10-29.md)。

## 收錄範圍

- 指定清單：https://www.nkust.edu.tw/p/422-1000-1001.php 。
- 官方 RSS：https://www.nkust.edu.tw/p/503-1000-1001.php 。實查回傳 20 則近期公告，不代表歷史全量。
- 全部收錄指定來源取得的公告。學生相關、分類不影響收錄，未知公告仍保存在「全部」。
- 摘要只來自來源提供的文字，可能截短；未提供發布時間時顯示未知，不用抓取日猜日期。
- 不自動抓取處室全文、附件，也不使用 AI。只有指定清單內資料，不保證涵蓋全校或所有 Gmail 通知。

## 安裝與資料庫

多人網站仍由 `app.web:app` 啟動，使用 `requirements-web.txt`，新增 `defusedxml==0.7.1`。
執行開發測試則安裝 `requirements-dev.txt`；鎖定環境使用 `requirements-lock.txt` 時也需有 defusedxml。

本分支 migration head 是 **0007**；0006 是公開公告版本，0007 新增私人修正快照／歷史表。本次沒有執行正式遷移。請先依 Phase 9 手冊備份資料庫與金鑰，再在確認的目的多人庫執行：

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

初期沒有自動更新排程，也沒有匿名「立即更新」端點。維護者需自行執行 CLI；
頁面提供真實最後成功更新、近期失敗及收錄範圍，不承諾每天或即時更新。
Render Free 會休眠，不能只靠 web 程序內背景迴圈提供可靠排程。

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

`/` 為免登入首頁，`/public/announcements` 為公開清單，`/public/announcements/{id}` 為詳情。
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
