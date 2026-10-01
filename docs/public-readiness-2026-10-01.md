# 開放使用檢查：2026-10-01

結論：目前不能確認可全面開放給其他人。資料說明、帳號隔離、刪除功能與 PostgreSQL 實機測試揭露的鎖定補修已發布。Google 對外授權與適用驗證、Neon 還原及營運驗收仍待完成。

## 已修正與驗證

| 問題 | 修正與驗證 |
| --- | --- |
| 登入前沒有資料使用說明 | 新增公開 `/privacy` 與登入頁連結，說明 Gmail 唯讀、同步範圍、資料保存、分類規則及解除授權。 |
| 無法自行刪除本站資料 | 帳號設定提供明確確認表單，驗證登入、來源及 CSRF。刪除自己的帳號、郵件、公告、衍生資料、授權與全部 session；嘗試撤銷 Google 授權，失敗仍完成本站刪除並提示手動解除。 |
| 刪除與同步／重新授權衝突 | 使用同一帳號作業 lease，防止同步時刪除、撤銷期間更換授權；繁忙時保留帳號與憑證並顯示可重試頁面。 |
| SQLite 編號重用導致舊請求越權 | 以 Google 固定帳號識別碼綁定 session 建立、公告讀取／統計、同步寫入、刪除與 Gmail 憑證。SQL 於同一查詢比較身分，避免先檢查再讀取的間隙。合成案例涵蓋舊請求讀寫新帳號與 SDK 偷用新帳號 token。 |
| 郵件 MIME 解碼缺少上限 | 限制共 2 MiB 本文、32 層 MIME 深度及 200 個部分；先檢查宣告大小再下載本文附件。過大郵件安全標記失敗，不暴露原文或憑證。 |

以上刪除與跨帳號測試只使用合成資料，未刪除任何真實帳號或 Gmail 郵件。本次修正不需要資料庫 migration，head 維持 0005。

## 驗證證據與限制

- 初次完整 pytest：357 passed、12 skipped、2 個既有棄用警告。12 項跳過當時尚未設定 `NKUST_TEST_POSTGRES_URL`；後續獨立實機測試結果見下方。
- PostgreSQL migration／查詢離線編譯通過；後續實機併發測試揭露了補修項目，見下方。
- `pip-audit -r requirements-web.txt` 成功，2026-10-01 解析的 50 個相依套件未發現已知漏洞。這是 Windows／Python 3.14 的解析結果，不等同 Render 已安裝環境的證明；部署時仍須掃描目標環境。JSON 報告在忽略的 `data/web-dependency-audit.json`。
- 再次查詢正式 `/login` 回傳 HTTP 200、`Cache-Control: no-store` 及 CSP。首次探測 30 秒逾時；第二次成功，僅證明當時登入頁可用，不代表登入、Gmail 同步或資料庫健康已驗收。
- 獨立程式複查已重現原隔離問題，修正後舊請求的詳細頁為 404、清單無他人公告、統計為 0，舊 Gmail 客戶端拒絕取用新帳號 token。
- 本地 `http://127.0.0.1:8001/preview` 使用獨立合成 SQLite 與假授權。它只展示真實模板與帳號控制介面，不能驗證 Google 登入／同步。

## 全面開放前尚待完成

1. **Google OAuth 對外授權與驗證**：擁有者已完成 Cloud Console 身分驗證。已確認專案 `nkust-mail-assistant` 的使用者類型為 External、發布狀態為 Testing，名單只有 1 位測試使用者。品牌首頁與隱私政策連結已儲存，發布按鈕已可使用，但未點選發布。驗證中心顯示因仍在測試模式而不需驗證，這不是已通過公開應用驗證。Web 用戶端已登錄正式 callback `https://nkust-mail-assistant.onrender.com/auth/google/callback`。需完成適用的 Google 驗證；不得僅因網站可開啟就認定任何人都能登入。
2. **隱私說明與備份策略已補齊現況**：擁有者已確認沿用 Google 現有支援信箱作為公開聯絡方式，並選擇保留 Neon 免費方案的 6 小時歷史還原。聯絡方式、主機／資料庫供應商、區域與還原現況已發布至 `/privacy`；OAuth 品牌已儲存可公開讀取的首頁與隱私說明連結。這不表示已通過 Google 隱私或 restricted-scope 驗證。
3. **Neon 還原與金鑰備份**：已在獨立本機 PostgreSQL 測試庫執行遷移、隔離、刪除及併發合約；仍須驗證正式 Neon 專案的 6 小時歷史還原操作與金鑰備份。測試未連正式庫。
4. **目標主機驗收**：部署修正後重新驗證 HTTPS 登入、失效授權、同步、刪除、代理日誌與容量／速率控制，確認可接受的同時使用人數。

## Google 官方要求

本服務使用 `gmail.readonly`，Google 將它列為 restricted scope。公開應用需依適用情況完成 restricted-scope 驗證；伺服器保存或傳輸此類資料通常還涉及安全評估，是否符合例外需由實際 audience／用途確認，不能用本地測試替代。

- [Gmail scopes 與 restricted-scope 要求](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [Audience 與發布狀態](https://support.google.com/cloud/answer/15549945?hl=en)：Testing 限列入名單的最多 100 位測試使用者；包含 Gmail 權限的測試授權通常在 7 天後失效。
- [OAuth 品牌與首頁要求](https://support.google.com/cloud/answer/13807376?hl=en)

在上述項目未完成前，保留受控測試範圍；不要承諾對所有 Google 帳號穩定開放。

## Google Console 後續實查

2026-10-01 擁有者完成身分驗證後，初次唯讀查看 Google Auth Platform（發布後的變更見下方紀錄）：

- Audience：External／Testing；只有 1 位測試使用者。未列入名單的其他人目前不能授權。
- Branding：應用程式名稱與使用者支援信箱已有設定，首頁與隱私政策連結尚未填寫。服務條款連結亦為空白，未據此判定其為必要欄位。
- Data access：已宣告的 Gmail 權限為 `gmail.readonly`，列在 restricted scopes。正式送審前仍需將宣告範圍與實際請求的 `openid`、`email`、`profile` 一併核對。
- Verification center：顯示測試狀態不需驗證，尚無可證明公開驗證通過的狀態。
- OAuth clients：存在 Web 與 Desktop 用戶端；Web 用戶端詳細頁首次載入失敗，重試後成功。已登錄 `http://localhost:8000/auth/google/callback` 與 `https://nkust-mail-assistant.onrender.com/auth/google/callback`。僅確認 Console 登錄內容，未變更用戶端、密鑰或 URI。

初次實查未變更 Google 設定。擁有者後續明確確認「沿用 Google 支援信箱」，已將該信箱加入網站資料使用說明；網站發布後只更新品牌首頁與隱私政策連結，未新增測試使用者或發布 OAuth 應用程式。

## 主機與備份後續實查

2026-10-01 初次唯讀確認正式服務部署於 Render，區域 Oregon、Free compute，當時程式為 `6e4d9a3`。Render workspace 只有該網站服務，資料庫使用外部 Neon；後續修正版發布見下方紀錄。

Neon 專案 `Nkust Mail Assistant` 的 production branch：

- 方案：Free；資料庫區域 AWS Singapore；PostgreSQL 18。
- 歷史還原期限：6 小時。Backup & Restore 頁面亦顯示相同期限。
- 快照與排程：頁面顯示 `No snapshots, no schedule set`；排程需升級方案。
- 未執行還原、建立快照、複製分支或讀取郵件資料，亦未變更方案或付費。

擁有者已選擇「先保留免費方案的 6 小時歷史還原」，因此此次不升級方案、不建立排程備份。6 小時歷史還原不能視為已具備每日備份或 7 天保存；還原演練仍未完成。

參考：[Neon 官方方案文件](https://github.com/neondatabase/website/blob/main/content/docs/introduction/plans.md)、[Neon 備份與還原說明](https://neon.com/docs/postgres/backup-restore/branch-restore)。實際專案設定以本次控制台實查為準。

## 修正版發布與公開頁面驗證

2026-10-01 11:37（台灣時間），Render 顯示 `Deploy succeeded | Live`，啟動前檢查通過，應用程式啟動成功：

- 程式 revision：`f9da63730cde46505ba532a114a4fcf7ede8863f`。
- 部署 ID：`dep-dauta6u0tbcc73ckk9hg`；本次沒有新增 migration。
- 正式 `/privacy` 與 `/login` 均為 HTTP 200，`Cache-Control: no-store` 及 CSP 存在。資料說明包含已確認的聯絡信箱與 6 小時歷史還原。
- 未登入讀取 `/announcements` 與 `/settings` 回傳 303 至 `/login`；GET `/sync` 回傳 405，不會啟動同步。未執行真實帳號刪除或讀取郵件。
- Google Branding 儲存首頁 `https://nkust-mail-assistant.onrender.com/` 及隱私政策 `https://nkust-mail-assistant.onrender.com/privacy`，重新載入確認仍保留。Audience 仍為 External／Testing、1 位測試使用者，未切換 Production。

以上是首次發布與匿名頁面檢查，不取代真實登入、同步、跨帳號、Neon 歷史還原、目標環境漏洞與負載驗收。方案未升級，未啟用付費功能。

## 獨立 PostgreSQL 實機測試與補修

使用 EDB 提供的 PostgreSQL 18.6 可攜式官方套件，只在本機 `127.0.0.1:55432` 啟動。建立獨立 `nkust_disposable` 測試庫與非管理員帳號；所有案例在該庫的隨機 schema 中使用合成帳號與假 Google 回應，沒有連到 Neon 正式庫，也沒有真實 Gmail 郵件。

- 原有 12 項 PostgreSQL 合約與新增的 12 項帳號／併發合約共 24 項通過。新增合約涵蓋帳號刪除、身分綁定、重新授權、同步競爭與失效授權；一項鎖順序測試先在原碼重現失敗，修正後通過。
- 修正後完整 pytest 為 381 passed、0 skipped、2 個既有棄用警告；沒有任何案例使用正式 Neon 連線或真實 Gmail 帳號。
- 首輪有 6 項因 PostgreSQL fixture 的合成 subject 與現有同步合約不一致而失敗；已統一為 `google-a`／`google-b`。另一項指出 PostgreSQL 同時鎖住憑證與使用者列，使重連檢查等到逾時；改為只鎖憑證列，仍在同一查詢驗證 Google subject。
- 獨立複查發現刪除與同步搶鎖可能依相反順序進行。實機回歸測試確認原碼存在該交錯；現已統一先鎖使用者、再鎖同步 lease。
- 這些測試證明本機 PostgreSQL 18.6 的合成場景，不證明 Neon 正式資料的還原能力、真實 Google 授權或 Render 目標負載。測試資料庫與隨機密碼不屬於正式環境。

2026-10-01 14:03（台灣時間）補修版 `3496a57fd0f50642f120b490af3b77396cb256f8` 於 Render 顯示 Live，部署 ID 為 `dep-dauvec3ncjis738h7su0`。啟動前檢查與應用程式啟動成功；正式 `/login`、`/privacy` 回傳 HTTP 200，未登入讀取 `/announcements`、`/settings` 仍導向登入頁，四者均有 `no-store` 與 CSP。這是匿名頁面與啟動檢查；真實 Google 登入、同步、跨帳號與刪除仍需在正式環境驗收。
