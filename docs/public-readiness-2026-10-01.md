# 開放使用檢查：2026-10-01

結論：目前不能確認可全面開放給其他人。程式層發現的問題已修正並完成本地測試；Google 對外授權、完整隱私政策與營運驗收仍待完成。本次修正尚未部署，正式網站仍使用原先版本。

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

- 完整 pytest：357 passed、12 skipped、2 個既有棄用警告。12 項跳過均為未設定 `NKUST_TEST_POSTGRES_URL` 的實機 PostgreSQL 測試，不算通過。
- PostgreSQL migration／查詢離線編譯通過；仍不能取代實機併發鎖與回復驗證。
- `pip-audit -r requirements-web.txt` 成功，2026-10-01 解析的 50 個相依套件未發現已知漏洞。這是 Windows／Python 3.14 的解析結果，不等同 Render 已安裝環境的證明；部署時仍須掃描目標環境。JSON 報告在忽略的 `data/web-dependency-audit.json`。
- 再次查詢正式 `/login` 回傳 HTTP 200、`Cache-Control: no-store` 及 CSP。首次探測 30 秒逾時；第二次成功，僅證明當時登入頁可用，不代表登入、Gmail 同步或資料庫健康已驗收。
- 獨立程式複查已重現原隔離問題，修正後舊請求的詳細頁為 404、清單無他人公告、統計為 0，舊 Gmail 客戶端拒絕取用新帳號 token。
- 本地 `http://127.0.0.1:8001/preview` 使用獨立合成 SQLite 與假授權。它只展示真實模板與帳號控制介面，不能驗證 Google 登入／同步。

## 全面開放前尚待完成

1. **Google OAuth 對外授權與驗證**：擁有者已完成 Cloud Console 身分驗證。已確認專案 `nkust-mail-assistant` 的使用者類型為 External、發布狀態為 Testing，名單只有 1 位測試使用者。品牌的首頁與隱私政策連結空白，發布按鈕停用。驗證中心顯示因仍在測試模式而不需驗證，這不是已通過公開應用驗證。Web 用戶端已登錄正式 callback `https://nkust-mail-assistant.onrender.com/auth/google/callback`。需先完成品牌與適用的 Google 驗證；不得僅因網站可開啟就認定任何人都能登入。
2. **隱私說明與備份策略**：擁有者已確認沿用 Google 現有支援信箱作為公開聯絡方式，並選擇保留 Neon 免費方案的 6 小時歷史還原。已將聯絡方式、主機／資料庫供應商、區域與還原現況補入資料說明。發布本次修正後，再於 OAuth 品牌設定補入可公開讀取的首頁與隱私說明連結。這不表示已通過 Google 隱私或 restricted-scope 驗證。
3. **PostgreSQL 與備份**：在獨立測試庫執行實機測試，驗證真實兩帳號隔離、帳號刪除與同步競態、備份還原及金鑰備份。不得讓測試自動連正式庫。
4. **目標主機驗收**：部署修正後重新驗證 HTTPS 登入、失效授權、同步、刪除、代理日誌與容量／速率控制，確認可接受的同時使用人數。

## Google 官方要求

本服務使用 `gmail.readonly`，Google 將它列為 restricted scope。公開應用需依適用情況完成 restricted-scope 驗證；伺服器保存或傳輸此類資料通常還涉及安全評估，是否符合例外需由實際 audience／用途確認，不能用本地測試替代。

- [Gmail scopes 與 restricted-scope 要求](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [Audience 與發布狀態](https://support.google.com/cloud/answer/15549945?hl=en)：Testing 限列入名單的最多 100 位測試使用者；包含 Gmail 權限的測試授權通常在 7 天後失效。
- [OAuth 品牌與首頁要求](https://support.google.com/cloud/answer/13807376?hl=en)

在上述項目未完成前，保留受控測試範圍；不要承諾對所有 Google 帳號穩定開放。

## Google Console 後續實查

2026-10-01 擁有者完成身分驗證後，唯讀查看 Google Auth Platform：

- Audience：External／Testing；只有 1 位測試使用者。未列入名單的其他人目前不能授權。
- Branding：應用程式名稱與使用者支援信箱已有設定，首頁與隱私政策連結尚未填寫。服務條款連結亦為空白，未據此判定其為必要欄位。
- Data access：已宣告的 Gmail 權限為 `gmail.readonly`，列在 restricted scopes。正式送審前仍需將宣告範圍與實際請求的 `openid`、`email`、`profile` 一併核對。
- Verification center：顯示測試狀態不需驗證，尚無可證明公開驗證通過的狀態。
- OAuth clients：存在 Web 與 Desktop 用戶端；Web 用戶端詳細頁首次載入失敗，重試後成功。已登錄 `http://localhost:8000/auth/google/callback` 與 `https://nkust-mail-assistant.onrender.com/auth/google/callback`。僅確認 Console 登錄內容，未變更用戶端、密鑰或 URI。

此次未變更 Google 設定、未新增測試使用者、未發布應用程式。擁有者後續明確確認「沿用 Google 支援信箱」，已將該信箱加入網站資料使用說明。

## 主機與備份後續實查

2026-10-01 唯讀確認正式服務仍部署於 Render，區域 Oregon、Free compute，程式仍為 `6e4d9a3`。Render workspace 只有該網站服務，資料庫使用外部 Neon。

Neon 專案 `Nkust Mail Assistant` 的 production branch：

- 方案：Free；資料庫區域 AWS Singapore；PostgreSQL 18。
- 歷史還原期限：6 小時。Backup & Restore 頁面亦顯示相同期限。
- 快照與排程：頁面顯示 `No snapshots, no schedule set`；排程需升級方案。
- 未執行還原、建立快照、複製分支或讀取郵件資料，亦未變更方案或付費。

擁有者已選擇「先保留免費方案的 6 小時歷史還原」，因此此次不升級方案、不建立排程備份。6 小時歷史還原不能視為已具備每日備份或 7 天保存；還原演練仍未完成。

參考：[Neon 官方方案文件](https://github.com/neondatabase/website/blob/main/content/docs/introduction/plans.md)、[Neon 備份與還原說明](https://neon.com/docs/postgres/backup-restore/branch-restore)。實際專案設定以本次控制台實查為準。
