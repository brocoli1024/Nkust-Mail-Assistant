# NKUST 校園郵件智慧助手

將 Gmail 中的高科大校園通知拆成可搜尋的公告，在本機查看原文、活動日期與截止日；可選擇使用 iAI 產生摘要，或擷取公告連結補充內容。

**第一次使用：先完成第 1 章的離線測試，再設定 Gmail。AI 是選用功能。**

| 你想做的事 | 從這裡開始 | 預估時間 |
| --- | --- | --- |
| 安裝並確認能執行 | [1. 安裝與離線試跑](#install) | 5–10 分鐘 |
| 匯入自己的校園郵件 | [2. Gmail 授權與同步](#gmail) | 15–25 分鐘 |
| 用網頁查看公告 | [3. 啟動與使用 Dashboard](#dashboard) | 2–5 分鐘 |
| 使用 AI 或補充網頁內容 | [4. iAI 分析](#ai)、[5. 網頁擷取](#scrape) | 設定約 5–10 分鐘 |
| 查設定或排除問題 | [6. 設定表](#settings)、[7. 常用指令](#commands)、[8. 故障排除](#troubleshooting) | 依問題而定 |

維護與開發：[9. 資料與金鑰保護](#privacy) · [10. 開發與 API](#development) · [11. 功能限制](#limitations)

## 功能與資料流

```text
Gmail（唯讀）→ 郵件解析 → 本機 SQLite → 瀏覽器 Dashboard
                           ↑
              手動擷取公告網頁／手動送交 iAI 分析
```

| 功能 | 操作結果 | 是否需要連網 |
| --- | --- | --- |
| 離線解析 | 從合成 HTML／文字樣本輸出公告 JSON | 否 |
| Gmail 同步 | 搜尋郵件、拆分公告、保存原文並略過已完成郵件 | 是，連到 Google |
| Dashboard | 查看本機公告、篩選分類、搜尋主旨與寄件單位 | 查看已存資料不需要 |
| iAI 分析 | 產生摘要、分類、關鍵字與行動判斷 | 是，公告文字會傳至 iAI |
| 網頁擷取 | 下載單則公告連結的正文，另存為補充資料 | 是，連到公告網站 |

Gmail 權限固定為 `gmail.readonly`，不寄信、不刪信、不修改信件或標籤。開啟 Dashboard 不會自動同步 Gmail、擷取網站或呼叫 AI。

<a id="install"></a>
## 1. 安裝與離線試跑

### 1.1 準備環境

本教學以 **Windows PowerShell** 為主，專案曾於 Windows、Python 3.14 執行測試。其他 Python 版本與作業系統需自行驗證套件相容性。

安裝 Python 與 Git 後，開啟新的 PowerShell，確認指令可用：

```powershell
python --version
git --version
```

後續指令都在專案根目錄執行，也就是看得到 `README.md`、`app` 與 `requirements.txt` 的資料夾。

### 1.2 下載專案

```powershell
git clone https://github.com/brocoli1024/Nkust-Mail-Assistant.git
cd Nkust-Mail-Assistant
```

如果你已經有這份專案，直接進入原本的資料夾，跳過 clone。也可從 GitHub 的 **Code → Download ZIP** 下載並解壓縮；ZIP 版本無法直接使用 `git pull` 更新。

### 1.3 建立虛擬環境並安裝套件

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

本教學直接指定虛擬環境的 Python，不需要執行 `Activate.ps1`，也不需要修改 PowerShell 執行原則。

| 套件清單 | 適用情況 |
| --- | --- |
| `requirements-dev.txt` | 本教學使用；包含執行套件與 pytest |
| `requirements.txt` | 只執行程式，不跑測試 |
| `requirements-lock.txt` | 安裝專案記錄的精確版本，包含測試套件；仍須符合平台相容性 |

若要使用鎖定版本，在虛擬環境中改執行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

### 1.4 執行離線驗證

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m app.cli parse tests/fixtures/nkust_mail_sample.html --received-at 2026-09-19
```

**成功判斷：**測試結束顯示 `passed`，解析指令輸出包含 3 則合成公告的 JSON。這兩個指令不需要 Gmail 授權或 AI 金鑰，也不會把範例寫入資料庫。

也可以解析純文字樣本：

```powershell
.\.venv\Scripts\python.exe -m app.cli parse tests/fixtures/nkust_mail_sample.txt --received-at 2026-09-19
```

`--received-at` 用來補足公告中省略的年份；請傳入信件實際收件日期。未提供時，缺少年份的日期會保留原文並附提醒，不使用今天的年份猜測。

### 1.5 建立本機設定檔

以下寫法只在 `.env` 不存在時建立檔案，保留你已有的設定：

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

用文字編輯器開啟 `.env`。先保留預設值即可；`AI_API_KEY` 與 `AI_MODEL` 可保持空白，等第 4 章再設定。請勿將 `.env` 的內容貼到 GitHub、Issue 或聊天中。

<details>
<summary>macOS／Linux 指令對照</summary>

以下為對應寫法，本專案主要驗證環境是 Windows：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m app.cli parse tests/fixtures/nkust_mail_sample.html --received-at 2026-09-19
```

後續將 `.\.venv\Scripts\python.exe` 換成 `.venv/bin/python` 即可。

</details>

<a id="gmail"></a>
## 2. Gmail 授權與同步

需要一個能收到校園通知的 Gmail 帳號，以及可建立 OAuth 用戶端的 Google Cloud 專案。OAuth 是讓程式取得你同意的讀取權限，不需要把 Gmail 密碼寫入專案。

### 2.1 建立 Google Cloud 專案並啟用 Gmail API

1. 開啟 [Google Cloud Console](https://console.cloud.google.com/)，建立或選取專案，例如 `NKUST Mail Assistant`。
2. 在同一專案中開啟 [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com)，按「啟用」。

### 2.2 設定 OAuth 同意畫面

1. 進入 **Google Auth Platform → Branding**，首次使用按 **Get started**，填寫應用程式名稱、支援信箱與聯絡信箱。
2. 在 **Audience** 設定使用對象。個人 Gmail 使用 **External**；組織帳號是否能使用 **Internal** 取決於組織設定。
3. 個人測試使用 **Testing** 狀態，將實際要讀信的帳號加入 **Test users**。
4. 在 **Data Access** 加入以下唯讀 scope，不加入寄信或修改權限：

```text
https://www.googleapis.com/auth/gmail.readonly
```

若學校或組織管理員封鎖此類存取，需先向管理員確認允許的授權方式。

### 2.3 建立桌面 OAuth 用戶端

1. 進入 **Google Auth Platform → Clients → Create client**。
2. **Application type** 選 **Desktop app**，填入名稱並建立。
3. 下載 JSON，重新命名為 `credentials.json`，放在專案根目錄，與 `README.md` 同層。

本專案使用桌面授權流程，不要選成 Web application，也不需自行填寫 Web 用戶端的 redirect URI。

Google 介面可能調整；建立流程可對照 [Google 官方 Gmail Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python) 與 [OAuth 同意畫面指南](https://developers.google.com/workspace/guides/configure-oauth-consent)。本專案程式已包含 API 呼叫，不必再複製官方 quickstart 的 Python 範例。

### 2.4 確認搜尋條件並完成授權

`.env` 預設讀取這個寄件來源：

```dotenv
GMAIL_QUERY=from:mailoffice@nkust.edu.tw
GMAIL_CREDENTIALS_PATH=credentials.json
GMAIL_TOKEN_PATH=token.json
```

先在 Gmail 網頁的搜尋欄貼上 `from:mailoffice@nkust.edu.tw`，確認有找到校園通知，再執行：

```powershell
.\.venv\Scripts\python.exe -m app.cli gmail --limit 5
```

瀏覽器開啟後，選擇已加入 Test users 的帳號並確認唯讀權限。程式最多等待 180 秒；逾時可重新執行。

**成功判斷：**終端機輸出郵件與公告 JSON，根目錄出現 `token.json`。這個指令只預覽，不寫入資料庫。JSON 可能含私人郵件內容，請勿直接公開分享。

### 2.5 同步至本機資料庫

```powershell
.\.venv\Scripts\python.exe -m app.cli sync --limit 5
```

預設自動建立 `data/nkust_mail.db` 與所需資料表，不必手動建立空白資料庫。

| 輸出欄位 | 意義 |
| --- | --- |
| `matched` | 本次搜尋找到、納入檢查的郵件數 |
| `processed` / `skipped` / `failed` | 成功處理、已完成而略過、失敗的郵件數 |
| `announcements_written` | 本次寫入公告數；重新解析時包含替換的公告 |
| `warnings` / `errors` | 解析提醒與逐封錯誤 |
| `database_counts` | 資料庫目前的統計 |

**成功判斷：**首次同步有符合格式的郵件時，`processed` 與 `announcements_written` 會增加；重跑相同指令，已完成的郵件會計入 `skipped`。

`--limit 5` 是「檢查最多 5 封符合搜尋條件的信」，包含已處理的信，不是「再新增 5 封」。要納入更多郵件可改成 `--limit 50`，或調整 `GMAIL_QUERY`。同一封彙整通知可能拆出多則公告，因此郵件數與公告數不同。

<a id="dashboard"></a>
## 3. 啟動與使用 Dashboard

### 3.1 啟動本機服務

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

保持終端機開啟，在瀏覽器前往 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**。停止服務時回到終端機按 `Ctrl+C`。

第一次尚未同步時，公告列表是空的；第 1 章的離線解析不會匯入示範資料。

此服務供單人本機使用，沒有使用者登入或多租戶隔離。請維持 `127.0.0.1`，不要直接改綁 `0.0.0.0` 或公開部署。GitHub 上傳的是原始碼，不會自動啟動這個 Python 服務。

### 3.2 日常操作

1. 選擇「同步最近」5／20／50／100 封，按 **同步 Gmail**。
2. 從側欄選 **全部公告、今日收到、即將截止、需要處理、AI／科技、就業／實習**。
3. 使用分類與主旨搜尋縮小範圍；切換側欄視圖仍會保留這些篩選條件。
4. 點公告主旨，查看原文、日期依據與已有的 AI 結果。

統計以台北時間計算。「今日收到」依郵件收件日；「即將截止」是今天起 7 天內。尚未分析的行動需求可能為未知，不代表沒有需要處理的公告。

同步、分析、擷取在同一服務程序共用作業鎖。請使用單一服務程序，不加 `--workers`，也不要同時用 CLI 同步同一資料庫。關閉網頁不會取消已經開始的作業。

### 3.3 下次使用

在專案資料夾執行 3.1 的啟動指令，開啟同一個網址即可。既有資料與設定會保留，不需要每次重新安裝或建立 `.env`。修改 `.env` 後，請停止並重新啟動服務。

<a id="ai"></a>
## 4. 設定 iAI 分析（選用）

沒有 AI 金鑰也能同步、搜尋、閱讀公告與查看規則解析的日期。

### 4.1 設定金鑰與查詢模型

登入高科大 iAI，取得自己帳號可用的 API Key，僅寫入本機 `.env`：

```dotenv
AI_PROVIDER=iai
AI_BASE_URL=https://www.iai.nkust.edu.tw/aihub/v1
AI_API_KEY=請在本機填入自己的金鑰
AI_MODEL=
AI_TIMEOUT_SECONDS=90
```

上面的中文是佔位文字，須在本機換成實際金鑰。不要將改好的內容複製回 `.env.example`。

查詢此帳號可用的模型：

```powershell
.\.venv\Scripts\python.exe -m app.cli ai-models
```

將輸出的完整模型 ID 填入 `AI_MODEL`，不要自行縮寫。專案過去曾驗證 `Furen-std`，但目前可用模型應以你的查詢結果為準；程式不會自動替換模型。

### 4.2 用合成公告測試

```powershell
.\.venv\Scripts\python.exe -m app.cli ai-check
```

**成功判斷：**輸出含 `provider`、`model`、`result` 與 `warnings` 的 JSON。此指令只把內建虛構公告送至 iAI，不讀取 Gmail 或資料庫，但仍會呼叫外部 API，可能消耗帳號額度。

完成後重新啟動 Dashboard。AI 狀態應顯示已設定的模型。

### 4.3 分析自己的公告

1. 按 **分析 5 則**，處理最多 5 則待分析公告。
2. 作業完成後，點開公告查看摘要、分類、關鍵字與判斷依據。
3. 若有失敗項目，先檢查服務或額度，再按 **重試失敗項目**。

分析批次依資料庫中符合條件的公告挑選，不限於目前畫面顯示或篩選的公告。要指定單則，請在詳情中按 **分析這則公告**。

同一模型與分析版本已完成的項目會略過；變更模型、分析版本或網頁內容後，可能需要再次分析。畫面的「已完成」統計不一定表示全部都由目前模型完成。

**資料會傳到哪裡？**按下分析時，公告單位、性質、主旨、原文、收件年份及日期資料會傳至設定的 iAI 端點；若已有網頁補充資料，也會包含補充文字及來源網址。不傳送 Gmail OAuth token 或整封信的 HTML，但原文本身若含姓名、電話等個資，仍會隨文字傳出。請依校方與模型服務說明確認使用範圍。

AI 的「需要處理」表示公告含申請、報名等可採取的行動，不代表你符合資格或一定要參加。截止日期、資格與重要決定仍應核對原文。

<a id="scrape"></a>
## 5. 擷取公告網頁（選用）

1. 打開一則帶有公告連結的詳情，按 **擷取網頁**。
2. 成功後查看補充正文與來源；原始郵件內容仍保留。
3. 若要讓 AI 使用補充文字，按 **分析這則公告**。
4. 網頁有更新時按 **重新擷取網頁**；內容改變後再分析，更新摘要。

擷取本身不會呼叫 AI。內容變更時會標記待分析，並保留舊摘要供對照；擷取失敗也會保留先前成功內容。

預設只允許 `officemail.nkust.edu.tw`。要加入另一個已確認的公告網站，在 `.env` 用逗號分隔**完整主機名稱**，不填協定或路徑：

```dotenv
SCRAPE_ALLOWED_HOSTS=officemail.nkust.edu.tw,announcements.example.edu
```

第二個網址是格式範例，請換成實際需要的網站，修改後重啟服務。允許某個網站不代表其所有版型都能解析。

只支援允許清單內的公開 HTTPS 網頁、443 埠；每次轉址也會檢查。登入頁、PDF、附件、未知正文版型與必須執行 JavaScript 的頁面不支援。正文上限 12,000 字；送給 AI 的標題與合併正文上限 16,000 字，超過會報錯而非默默截斷。

<a id="settings"></a>
## 6. 設定參考

設定來源依序為 **系統環境變數 → `.env` → 程式預設值**。相對路徑以專案根目錄為基準。

### Gmail 與資料庫

| 變數 | 預設值 | 用途 |
| --- | --- | --- |
| `GMAIL_QUERY` | `from:mailoffice@nkust.edu.tw` | Gmail 搜尋條件 |
| `GMAIL_CREDENTIALS_PATH` | `credentials.json` | Desktop OAuth 用戶端 JSON |
| `GMAIL_TOKEN_PATH` | `token.json` | 授權後產生的 token |
| `GMAIL_TIMEOUT_SECONDS` | `30` | Gmail 請求逾時秒數，須大於 0 |
| `DATABASE_PATH` | `data/nkust_mail.db` | 本機 SQLite 檔案位置 |

### AI

| 變數 | 預設值 | 用途 |
| --- | --- | --- |
| `AI_PROVIDER` | `iai` | 目前僅支援 iAI adapter |
| `AI_BASE_URL` | `https://www.iai.nkust.edu.tw/aihub/v1` | HTTPS API 基底網址 |
| `AI_API_KEY` | 空白 | 僅填於本機的金鑰 |
| `AI_MODEL` | 空白 | `ai-models` 查到的完整模型 ID |
| `AI_TIMEOUT_SECONDS` | `90` | AI 請求逾時，允許 1–300 秒 |

### 網頁擷取

| 變數 | 預設值 | 用途 |
| --- | --- | --- |
| `SCRAPE_ALLOWED_HOSTS` | `officemail.nkust.edu.tw` | 逗號分隔的精確主機清單，不支援萬用字元 |

Gmail 的唯讀 scope 固定在程式中，不能用 `.env` 擴大權限。變更金鑰或 AI 端點前，請確認該端點是你信任的服務，因為 API 金鑰會送往這個位址。

<a id="commands"></a>
## 7. 常用指令

以下指令都在專案根目錄執行。

| 用途 | PowerShell 指令 |
| --- | --- |
| 查看 CLI 說明 | `.\.venv\Scripts\python.exe -m app.cli --help` |
| 預覽 5 封，不存入資料庫 | `.\.venv\Scripts\python.exe -m app.cli gmail --limit 5` |
| 同步最多 50 封 | `.\.venv\Scripts\python.exe -m app.cli sync --limit 50` |
| 查詢 AI 模型 | `.\.venv\Scripts\python.exe -m app.cli ai-models` |
| 測試 AI 連線與格式 | `.\.venv\Scripts\python.exe -m app.cli ai-check` |

### 重新解析既有郵件

先停止 Dashboard，確認需要替換既有解析結果，再執行：

```powershell
.\.venv\Scripts\python.exe -m app.cli sync --limit 5 --reparse
```

`--reparse` 會替換選中郵件的公告列，公告 ID 可能改變，相關 AI 分析與網頁擷取紀錄也會隨舊公告清除。若替換過程失敗，該封郵件的舊資料會保留。需要保留現況時，先依第 9 章備份資料庫。

### 更新程式

停止服務後，在沒有待處理本機程式修改的情況下執行：

```powershell
git pull --ff-only
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

確認測試通過再啟動 Dashboard。若 Git 提示本機變更或分支分歧，先保存並處理修改，不要直接使用強制覆寫指令。

<a id="troubleshooting"></a>
## 8. 故障排除

### 安裝與啟動

| 現象 | 處理方式 |
| --- | --- |
| 找不到 `python` 或 `git` | 確認已安裝且加入 PATH，重新開啟 PowerShell |
| `ModuleNotFoundError` | 使用本教學的 `.venv` Python，重新安裝 `requirements-dev.txt` |
| 套件安裝失敗 | 檢查 Python 版本、網路與平台套件支援；保留錯誤訊息但先移除私人路徑或憑證內容 |
| 8000 埠已被占用 | 關閉舊服務，或將啟動指令改成 `--port 8001`，瀏覽器也改用 8001 |
| 修改 `.env` 後沒生效 | 重啟服務；若仍不符，檢查同名系統環境變數是否覆蓋 `.env` |

### Gmail

| 現象 | 處理方式 |
| --- | --- |
| `OAUTH_SETUP_REQUIRED` | 確認 `credentials.json` 存在，且 `.env` 指向正確路徑 |
| `OAUTH_CLIENT_TYPE` | 重新建立 **Desktop app** OAuth 用戶端 |
| `OAUTH_SCOPE_MISMATCH` | 使用獨立唯讀用戶端與新的 token 路徑，例如 `token-readonly.json`，不要沿用其他程式的廣泛權限 token |
| `OAUTH_FAILED`／Google 拒絕登入 | 檢查 Test users、帳號、網路、授權是否過期或撤銷，以及組織管理限制 |
| `matched` 為 0／同步一直略過 | 在 Gmail 網頁驗證相同搜尋式；已同步的信會略過，增加 limit 才能涵蓋更多郵件 |

若確認是舊 token 無法更新：停止服務，在 `.env` 將 `GMAIL_TOKEN_PATH` 改為尚未存在的 `token-readonly-new.json`，重跑 `gmail --limit 5` 重新授權。舊 token 仍是敏感資料，不要公開分享。此命名符合目前 `token*.json*` 的忽略規則。

### AI 與網頁擷取

| 現象 | 處理方式 |
| --- | --- |
| AI 顯示尚未設定 | 確認金鑰、模型已填，先跑 `ai-models`／`ai-check`，再重啟 |
| `AI_HTTP_ERROR`／`AI_TIMEOUT`／`AI_CONNECTION_FAILED` | 檢查金鑰、模型存取權、額度、服務與網路；必要時調整 timeout 後重試 |
| AI 格式或驗證失敗 | 確認模型支援 Chat Completions 與 JSON 輸出；檢查原文，不能把未通過驗證當作成功 |
| 網址被擋／需要登入／不支援版型 | 確認允許清單；需登入或不支援的頁面請自行開啟閱讀 |
| 正文過長／非 HTML／憑證錯誤 | 直接閱讀來源頁或附件，不關閉憑證驗證來強制下載 |

### Dashboard 與資料庫

| 現象 | 處理方式 |
| --- | --- |
| 列表是空的 | 先同步；清除搜尋與分類，切回全部公告；確認讀取正確資料庫 |
| 「需要處理」為空 | 可能尚未分析或判斷未知，先查看全部公告與原文 |
| HTTP 409 | 已有同步、分析或擷取作業，等候完成再操作；重新整理不會取消工作 |
| HTTP 403／Invalid host header | 使用 `127.0.0.1` 或 `localhost` 開啟 Dashboard；寫入 API 需專案自訂標頭與同來源 |
| `DATABASE_ERROR`／資料庫暫時無法存取 | 確認路徑可寫、磁碟空間足夠，且沒有其他服務或 CLI 同時操作 |

回報問題時提供執行指令、Python 版本、錯誤代碼與重現步驟；不要附上 `.env`、OAuth JSON、資料庫或真實郵件全文。

<a id="privacy"></a>
## 9. 資料保存、備份與金鑰保護

### 哪些檔案只留在本機？

| 檔案或目錄 | 內容 | Git 處理 |
| --- | --- | --- |
| `.env` | 本機設定與 AI 金鑰 | 忽略；僅提交空白金鑰的 `.env.example` |
| `credentials*.json`、`client_secret*.json` 與其備份 | Google OAuth 用戶端憑證 | 忽略 |
| `token*.json*` | Gmail access／refresh token | 忽略 |
| `*.db`、`*.db-*`、`*.sqlite*`、`data/samples/private/` | 郵件原文、公告、AI 結果與私人樣本 | 忽略 |
| 私鑰檔、`secrets/`、`*.log`、`.venv/` | 金鑰、記錄或本機依賴 | 由 `.gitignore` 排除 |

**SQLite 含私人郵件原文，且程式沒有替資料庫加密。**請使用受保護的本機位置。若專案放在 OneDrive 等同步資料夾，檔案仍可能被該服務同步；`.gitignore` 只影響 Git，不會阻止其他同步軟體。

### 上傳 GitHub 前檢查

```powershell
git status --short
git check-ignore .env credentials.json token.json data/nkust_mail.db
git diff --cached --name-only
```

預設敏感檔案應被 `check-ignore` 列出，且不出現在待提交清單。自訂憑證名稱、匯出 JSON 或其他備份位置不一定符合既有規則，請先補入 `.gitignore`。

`.gitignore` 不會自動取消已追蹤檔案，也無法辨識貼進程式碼中的金鑰。若金鑰曾被公開，應先撤銷或輪替，再處理 Git 歷史；只刪除目前版本不足以清除洩漏。

### 備份與還原

1. 停止 Dashboard，確認 CLI 同步、分析等工作也已結束。
2. 複製 `.env` 設定的資料庫檔案至受保護的位置；預設為 `data/nkust_mail.db`。
3. 若需備份 `.env` 與憑證，使用受保護的備份位置，不要放進公開儲存庫。
4. 還原時先停止服務，再讓 `DATABASE_PATH` 指向備份副本並重啟。

若資料庫旁仍有 `-wal` 或 `-shm` 檔案，請先確認相關程序已正常停止，不要在寫入期間只複製主檔。不要將私人備份放入 `tests/fixtures/`；該目錄只收合成或去識別化樣本。

<a id="development"></a>
## 10. 開發、測試與 API

### 專案結構

```text
app/
  cli.py                 # 命令列入口
  config.py              # 環境設定與固定唯讀 scope
  main.py                # FastAPI 與本機 Dashboard
  api/                   # 公告、同步、AI、擷取 API
  database/              # SQLite 初始化與交易
  models/                # 郵件、公告、分析、擷取資料表
  providers/             # iAI adapter 與 provider 契約
  schemas/               # AI 輸出格式
  services/              # Gmail、解析、同步、分析、擷取邏輯
  templates/             # Dashboard HTML
  static/                # CSS 與 JavaScript
tests/
  fixtures/              # 合成測資
  test_*.py              # 離線測試
data/samples/README.md   # 私人樣本保存規則
.env.example             # 可公開的設定範本，不含真實金鑰
```

### 測試方式

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

測試涵蓋 MIME 解碼、公告與日期解析、OAuth 模擬、SQLite 原子寫入、重複同步、API、AI 格式驗證及網頁擷取限制。離線測試不等同真實 Gmail 授權或外部 AI 可用性驗證。

擷取傳輸層使用 Scrapling 的內部 curl session 設定，因此目前固定 `scrapling[fetchers]==0.4.15`；升級時需重新確認傳輸與安全限制測試。

### API 參考

啟動服務後可在 [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) 查看 schema。Swagger 的預設 Try it out 不會自動附上專案自訂標頭，寫入操作建議使用 Dashboard 或下方範例。

| 唯讀端點 | 功能 |
| --- | --- |
| `GET /api/summary` | 今日數量、截止統計、行動未知數與最近成功時間 |
| `GET /api/announcements` | 列表；支援 `view`、`category`、`q`、`page`、`page_size` |
| `GET /api/announcements/{id}` | 原文、日期依據、分析與網頁補充結果 |
| `GET /api/ai/status` | 本機設定是否完整、模型與分析進度；不回傳金鑰 |

`view` 支援 `all`、`today`、`deadline`、`action`、`jobs`、`tech`。列表每頁預設 20 筆，上限 100。`q` 搜尋主旨與寄件單位；`category` 允許課程、選課、獎學金、競賽、講座、活動、證照、TOEIC、實習、徵才、交換學生、行政通知、其他。

| 寫入端點 | JSON 範例 | 限制 |
| --- | --- | --- |
| `POST /api/gmail/sync` | `{"limit":5}` | 1–100 封 |
| `POST /api/ai/analyze` | `{"limit":5,"retry_failed":false}` | 1–20 則，可另指定 `announcement_id` |
| `POST /api/announcements/{id}/scrape` | `{"refresh":false}` | `true` 表示重新擷取 |

寫入端點需要 `X-Requested-With: NKUST-Dashboard`；若請求帶有 `Origin`，也必須與服務來源相符。以下範例**會真的同步 Gmail**，請先完成授權：

```powershell
Invoke-RestMethod -Method Post `
  -Uri 'http://127.0.0.1:8000/api/gmail/sync' `
  -Headers @{ 'X-Requested-With' = 'NKUST-Dashboard' } `
  -ContentType 'application/json' `
  -Body '{"limit":5}'
```

### 資料一致性

每封郵件與其公告在同一交易寫入，失敗時回滾；不同郵件分開處理。Gmail message ID 與郵件內的公告序號用於避免重複。Fingerprint 供來源追蹤，不會將不同郵件內文字相同的公告合併。

重新解析會替換所選郵件的公告；分析與擷取遇到原始資料已變更時會避免把舊結果寫入新資料。純略過的同步不會更新「最近成功處理」時間。

<a id="limitations"></a>
## 11. 目前限制

1. **郵件格式有限：**主要處理校園彙整通知表格與指定標籤的純文字。未知版型、缺欄或合併儲存格可能明確解析失敗。
2. **日期與 AI 需核對：**日期不確定時保留未知與提醒；AI 有格式和引用驗證，但不保證摘要或語意正確，規則辨識日期優先。
3. **擷取不等同瀏覽器：**不登入網站、不遞迴爬取、不處理 PDF／附件，也不執行網頁 JavaScript。
4. **本機單人使用：**沒有帳號登入、多使用者隔離、背景排程或自動寄送通知；同步、分析、擷取需手動啟動。
5. **外部服務需自行設定：**Gmail OAuth 與 iAI 的可用性、帳號權限、額度與資料政策由相關服務決定。
