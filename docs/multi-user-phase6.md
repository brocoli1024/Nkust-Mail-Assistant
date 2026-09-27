# Phase 6：Dashboard ownership filtering

新增 `app/api/user_announcements.py`，只由多人 `app.web` 掛載。舊版 routes、parser、資料庫及 token.json 不變，沒有 schema migration。

- Dashboard 的全部、今日收到、即將截止、需要處理統計皆限制 session 使用者。
- `/announcements` 提供分類、範圍與每頁 20 則的穩定分頁；`/announcements/{id}` 提供原文、來源、日期及可用的 HTTP(S) 連結。
- 每個查詢同時限制 Announcement.user_id 與 Email.user_id；join 也包含 owner 條件。其他人的 ID 與不存在的 ID 同樣回 404。未登入 HTML 頁面導回登入。
- 今日以台灣午夜換算 UTC 比較 received_at，不使用 SQLite 專屬日期函式。七天內截止為今天至今天加六天，包含兩端。需要處理只計入 requires_action=True，NULL 明確顯示尚未判定。
- 分類只使用已存 category，NULL 顯示未分類；不啟用 AI，不根據主旨假裝分類完成。
- Jinja 自動跳脫純文字原文，不渲染 original_html 或完整郵件 body；來源連結僅允許無帳密的 HTTP(S)，新分頁連結不帶 referrer。回應維持 no-store、CSP。

修改 session.py、web.py、account.html、account.css；新增清單及詳細頁 template、test_announcements_auth.py。本階段測試涵蓋雙向隔離、相同 Gmail ID、匿名存取、404 一致性、統計、台灣日期邊界、分類、分頁、未知值、HTML 跳脫與連結協定檢查。

手動驗收：登入後開 Dashboard，點全部公告、變更分類、開啟一則公告查看原文。只讀取已同步資料，不自動同步 Gmail。Phase 7 的全面安全測試與 Phase 8 PostgreSQL 實機整合尚未執行。
