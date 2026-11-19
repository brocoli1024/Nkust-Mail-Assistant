# 四項補修與獨立 PostgreSQL 驗收

收尾日期：2026-10-31（Asia/Taipei）。產品修正與完整驗收於前次執行完成，本次確認改動仍在、測試資料庫已停止，補齊文件及本機提交。未部署、push、變更正式資料庫或OAuth。

## 四項修正

1. source_views：候選包含一般HTTPS及明列預設埠443的網址，之後仍逐筆以official_identity精確驗證；保留owner限制及先比對再分頁，雙向入口都能列出來源。
2. web：公開頁500／503重試保留本站原路徑與查詢，路徑特殊字元編碼，模板跳脫查詢，維持origin-relative URL；404／422仍返回清單以修正條件。
3. action-card.js：重新繪製依據時保留來源標題／來源摘要／郵件公告原文的種類標籤，以textContent安全呈現。
4. 私人公告詳情：顯示既有收到時間（台灣時間）與原始分類，未知分類顯示未提供；分類由模板跳脫。

## 驗證證據

四項缺口先由回歸測試重現失敗，再修正轉為通過。相關Python頁面測試45 passed；Node calendar_integration_check的依據標籤驗證由失敗轉為通過。六項Node回歸均通過：calendar_integration_check、calendar_ics_check、todo_store_check、action_card_store_check、announcement_filter_check、pwa_worker_check。

完整測試在獨立PostgreSQL 18.6執行：**571 passed、0 skipped、2 warnings，174.46秒，SUITE_EXIT=0**。原本49項略過的PostgreSQL合約均實際執行，涵蓋schema metadata、遷移／降級重建、owner隔離、同步lease、帳號刪除鎖順序、私人修正競爭、待辦競爭、重新解析保留與來源版本A→B→A。兩項警告是既有Starlette/httpx與anyio棄用提示。

使用既有可攜式PostgreSQL工具建立全新隨機臨時cluster，僅監聽127.0.0.1，使用隨機密碼與非管理員qa_test帳號、獨立nkust_disposable庫；各測試再建立隨機schema並清理。連線只以子程序NKUST_TEST_POSTGRES_URL傳入，不取正式DATABASE_URL。初次Windows背景程序管線等待問題已調整，不涉及產品修正。

測試程序已回報Disposable PostgreSQL stopped且exit0；2026-10-31另查無postgres.exe／pg_ctl.exe程序。臨時合成cluster保留但已停止，密碼檔由啟動程式清除；沒有憑證寫入儲存庫。

## 獨立審查

four_gaps_review唯讀檢查八個變更檔案與周邊程式，另跑Node整合測試通過；Critical／Important／Minor皆無，結論可整合（完整測試亦已通過）。審查未判斷未追蹤的舊audit文件及被忽略的臨時PG啟動器：兩者由執行者核對，前者保留歷史並附最新狀態，後者僅合成驗收、未納入產品或提交。沒有未處理的四項補修問題。

## 仍然適用的限制

本機PostgreSQL合約通過不代表正式Neon備份還原、Render負載或真實Google授權已驗收。本次未新增實體手機、螢幕閱讀器或停用JS的瀏覽器驗收；沿用之前320／390畫面與帳號隔離證據。大量同URL來源的記憶體成本、版本累積容量仍需按預期使用量驗收。功能仍保留本機worktree，正式發布需另行授權與安排。
