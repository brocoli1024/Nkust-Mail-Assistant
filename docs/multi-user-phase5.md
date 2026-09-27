# Phase 5：多人 Gmail 同步

## 使用方式

登入 `app.web:app` 後，Dashboard 提供「同步最近 5 封校園通知」按鈕。只有按下按鈕才讀取 Gmail；頁面載入、登入、設定頁都不會自動同步。結果頁顯示找到、處理、略過、失敗與建立公告數。公告列表與詳細資料仍留到 Phase 6。

API 是 `POST /sync`，需要有效 session cookie 與 `X-CSRF-Token`（取自同一 session 的頁面表單），JSON body 為 `{"limit": 5}`。limit 預設 5、最多 100，拒絕 `user_id`、`force` 或其他未知欄位。傳入的 session 是唯一身分來源，不能指定其他帳號。表單亦支援 hidden `csrf_token`，回傳 HTML 結果。

範例結果：

```json
{
  "emails_found": 5,
  "emails_processed": 4,
  "emails_skipped": 0,
  "emails_failed": 1,
  "announcements_created": 37,
  "reauthorization_required": false,
  "errors": [{"gmail_message_id": "example", "error": "TABLE_NOT_FOUND", "failure_recorded": true}],
  "database_counts": {"emails": 5, "announcements": 37, "failed_emails": 1}
}
```

結果只含目前使用者的計數；error 是固定代碼，不含原始 provider response、SQL 參數、郵件本文或 token。failure_recorded=false 表示連失敗紀錄都未能寫入，之後需重試。warnings 與解析證據保存在該使用者資料中，不放入同步 API 回應。

## 同步與儲存

`UserSyncService.sync_gmail_for_user(user)` 組合 Phase 4 的 Gmail factory、使用者範圍 repository，以及**原有 SyncService 與所有 parser**。搜尋固定 `from:mailoffice@nkust.edu.tw`。

- 所有 Email 查詢以 user_id＋gmail_message_id 篩選；Announcement 寫入／刪除與統計都限制 user_id，DB 複合外鍵再次檢查 ownership。
- 已成功處理且 parser_version 相同的信件在下載本文前略過。同一使用者不重複增加 Email；不同使用者可各自保存相同 Gmail ID。
- 每封郵件與其公告使用一個交易。儲存失败全部回滾；另一個交易記錄 last_error；下一封繼續。
- Parser version 改變時重新解析。失敗保留原本成功快照；成功重建該封信的公告，並透過外鍵清理舊公告關聯。這沿用既有核心語意；未提供公開 force 參數，也不拿重新同步替代舊庫匯入。
- received_at 轉成 UTC datetime；活動日期／截止日期由 parser 的 ISO 字串轉 Date。summary／requires_action 未判定時仍為空，不啟用 AI。

## 並行控制

Migration `0004` 新增 `sync_leases`，user_id 為主鍵。同一使用者只能有一個持有者，其他請求回 409；不同使用者可各自取得 lease。這不是程序內 Lock，因此多個 app／worker 共用 DB 時仍有作用。

Lease 有 5 分鐘有效期，在每次檢查已處理／寫入／記錄失敗時續期。寫入交易第一步必須以 user_id＋owner＋未到期條件更新 lease；舊 worker 若已逾時或失去 ownership，不能寫入。釋放時也比對 owner，不能誤刪新 worker 的 lease。程序意外終止後，逾時 lease 可被下一個作業接手。

Gmail 長時間無回應可能讓 lease 到期，回 409 後重試即可；之前已完成的郵件仍保存，重試會跳過。SQLite 仍只有單一 writer，不同帳號的短資料庫交易可能等待；Google 網路 I/O 不持有該寫入交易。

## 錯誤與 HTTP 狀態

| 情況 | 回應 |
| --- | --- |
| 未登入／session 已失效 | 401，不連線 Gmail |
| CSRF／Origin 不符 | 403，不連線 Gmail |
| limit 或未知欄位錯誤 | 422；過大 body 413，不支援 media type 415 |
| 同帳號已有同步／lease 失效 | 409 |
| 建立 client／搜尋時授權失效 | 401 `GMAIL_REAUTHORIZE` |
| Credential provider 暫時故障 | 503 |
| Gmail 搜尋失敗 | 502 |
| 單封讀取／解析／儲存失敗 | 200，emails_failed 與 errors 明確記錄，其他郵件繼續 |

若授權在逐封讀取期間失效，會設 `reauthorization_required=true` 並在結果頁提供重新連結入口；部分成功資料仍保留。整個作業開始前 Gmail 搜尋失敗，沒有可處理的 ID，直接回上述錯誤。

## 檔案與驗證

新增 `app/database/user_mail.py`、`app/services/user_sync_service.py`、`app/api/sync.py`、`0004` migration、結果 template，以及 `test_sync_multi_user.py`／`test_sync_auth.py`。更新多人 model、web 啟動、Dashboard 同步表單與 README。舊版 parser、Gmail service、SyncService 與既有測試不變。

新增 24 項測試：兩使用者隔離、相同 Gmail ID、重複同步、逐封失败／重試、錯誤去敏感化、失敗重解析回滾、訊息 ID 不符、跨實例並行、過期 worker 防寫入、登入／CSRF／Origin／輸入驗證與 HTML 結果。測試使用合成郵件與假 Gmail，不讀取使用者的真實郵件。

部署前先備份**新的多人庫**，執行 `python -m alembic upgrade head` 至 `0004`，再重啟 `app.web:app`。原 `data/nkust_mail.db` 與 token.json 不需搬移或修改。PostgreSQL lease 使用原生 upsert；本階段僅做 SQLite 執行測試，真實 PostgreSQL 並行整合留待 Phase 8。

本階段停止於同步核心，不開放公告查詢。只有使用者明確按下同步按鈕才會執行真實 Gmail 驗證。
