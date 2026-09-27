# Phase 4：每位使用者自己的 Gmail client

## 完成範圍

新增 `app/services/user_gmail_service.py`，在 Web app 啟動時註冊 `app.state.gmail_for_user`。註冊工廠不會建立 Gmail 連線、更新 token 或讀取郵件。沒有新增同步 route／按鈕，沒有匯入或修改真實郵件資料。

既有 `gmail_service.py`、Desktop OAuth、CLI、MIME／公告／日期 parser 與既有測試維持原樣。多人 service 繼承既有讀取方法，僅替換 credential、錯誤處理及 client 生命週期。

## 後續呼叫方式

Phase 5 的 route 必須先透過 `current_user` dependency 取得 `CurrentUser`，再呼叫：

```python
with request.app.state.gmail_for_user(user) as gmail:
    ids = gmail.list_message_ids(limit=5)
    # 將此 gmail 與 user-scoped persistence 交給 Phase 5 sync service。
```

此片段會讀取 Gmail，只用於後續已授權的同步請求，不應在頁面載入時執行。工廠要求 `CurrentUser` 物件，拒絕前端 JSON、裸 user ID 與無效 ID；這個型別檢查不是 authentication 的替代品，route 仍必須先驗證 session。底層 `UserGmailService.connect(..., user_id=...)` 是內部介面，不可將 request 中的 user_id 直接傳入。

每次作業使用獨立 client／httplib2 transport，不跨使用者或 worker thread 共用；context manager 在結束時關閉 transport。使用 SDK 內建 discovery 文件，client 建立不會向 Gmail 查詢。不過缺少有效 access token 時，建立 client 可能先透過 Google OAuth refresh endpoint 更新授權。

## Credential 與錯誤處理

1. 從該 user 的 OAuthAccount 取得憑證；同時確認 provider_user_id 與 User.google_user_id 一致，並驗證 scope。
2. 每次 Gmail HTTP request 前從 token service 取得有效 token，於後端加入 Authorization header，不讀取全域 `token.json`／`credentials.json`。
3. Token 到期沿用 Phase 2 的 refresh 與加密保存；若收到 401，SDK 最多要求一次 refresh。若另一個 worker 已更新該 token，重用新版而不重複 refresh。
4. 再次 401、invalid_grant、帳號不存在、scope／密文異常會變成 `GmailReauthorizationRequired`。Phase 5 應提示該使用者重新連線 Google。網路／token provider／DB 暫時失敗變成 `GmailCredentialsUnavailable`；不能把暫時故障當作授權永久撤銷。
5. Gmail HTTP 錯誤只提供操作名稱與 status，不暴露 response body 或 chained exception。MIME parser 原本包裝的附件授權錯誤會由 adapter 還原為上述型別，parser 不需修改。

所有 Gmail resource requests 維持 `userId='me'`，`me` 是該 client token 所屬的 Gmail 帳號。搜尋固定 `from:mailoffice@nkust.edu.tw`，不套用舊版可自訂的 GMAIL_QUERY；只使用既有 list/get/attachments.get 讀取方法，沒有新增 modify/send 權限。

## 修改檔案

| 檔案 | 修改 |
| --- | --- |
| `app/services/user_gmail_service.py` | 新增 per-user factory、credential adapter、錯誤型別與生命週期 |
| `app/auth/token_service.py` | 驗證 user ID／Google subject 關聯；支援被 401 拒絕 token 的條件式 refresh |
| `app/web.py` | 註冊惰性 per-user Gmail 工廠 |
| `tests/test_user_gmail_service.py` | 使用真實 Gmail SDK、假 HTTP transport 及合成加密 DB 資料驗證 |
| README／本文件 | 記錄階段邊界與下一步接法 |

## 驗證與限制

新增 15 項測試，涵蓋兩使用者 token 分離、固定搜尋條件、禁止 Desktop fallback、refresh 持久化、401 上限、授權撤銷、scope／subject／密文不符、另一 worker 已更新 token、SDK 分頁、附件 MIME 解碼與錯誤去敏感化。所有測試均離線，沒有讀取真實 Gmail。

本階段不需要 schema migration 或 Google Cloud 設定變更。正在執行的服務需重新啟動才載入新工廠；由於尚未有 route 使用它，可在 Phase 5 啟動同步入口時一併重啟。仍待 Phase 5 實作 user-scoped sync／儲存／逐封失敗處理，Phase 6 才加入公告查詢與 Dashboard ownership filtering。
