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

進行中。各任務完成後補入實測結果；本文件不表示第一階段已完成。
