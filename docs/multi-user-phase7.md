# Phase 7：安全回歸測試

範圍為多人 Web 核心的自動化安全回歸。全部使用暫存 SQLite、合成資料、假的 Google／Gmail provider；不讀取真實 Gmail、不修改原資料庫或 token.json。

## 新增驗證

- `tests/test_user_isolation.py`：A、B 分別經 OAuth callback 建立 session；A 同步後 B 的清單／統計仍為空，不能以 ID 或 user_id query 取得 A 的公告。B 同步相同 Gmail ID 可獨立保存；B 登出後不能讀取，A session 仍可讀取且重複同步不增資料。實際使用既有 parser、同步與 SQL 儲存。
- `tests/test_security.py`：敏感檔案路徑與舊版 API 未暴露、錯誤參數不回顯、資料庫／未知例外不洩漏內容或 traceback、輪替前的 CSRF 不可同步或登出、畸形／過大／重複表單輸入被拒、Host 限制、登入不接受任意 next redirect、私人頁面 no-store 與 CSP 防嵌入。

共新增 26 個測試案例。首次執行 23 通過、3 失敗：FastAPI 預設參數錯誤回應會包含原始 input。`app/web.py` 新增 RequestValidationError handler，統一回 422 與固定訊息，不回傳原始參數、例外內容或詳細錯誤物件。這是輸入回顯問題，並非跨使用者資料洩漏。

## 沿用的安全覆蓋

現有測試繼續驗證 OAuth state／瀏覽器綁定／nonce／PKCE／一次性與過期、真實簽章驗證、issuer／audience／scope 限制、時間容差上限、session 輪替／撤銷／過期、production Cookie、CSRF／Origin、token 加密與 owner 綁定、refresh 失敗、Gmail 每帳號 client、資料庫複合外鍵、並行同步 lease、HTML 跳脫與來源 URL 限制。

## 限制

這是程式與測試範圍的檢查，不能視為完整滲透測試或正式部署認證。真實 PostgreSQL 整合、正式反向代理／TLS／存取日誌、部署資源限制與依賴漏洞掃描尚未驗證，留待後續明確階段。不要把 SQLite 的通過結果當作 PostgreSQL 實機通過。

本階段不變更 schema、不需要 Google Cloud 設定。需重啟 app.web 套用固定錯誤回應。完成後停在 Phase 7。

最終驗證：完整 pytest **309 passed**，另有 2 個既有 Starlette/httpx 棄用警告；git diff --check 無空白錯誤。服務已重啟，登入頁回 200、匿名公告清單回 303 至 /login。原單人資料庫及 token.json 的 SHA256 與修改前一致。
