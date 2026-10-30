# 第五階段驗證：來源關聯與版本留存

日期2026-10-30。範圍為本機隔離worktree，基準e7eaf67（第四階段）；未部署、push、修改正式DB/OAuth或啟用新服務。main單人版與codex/web-deployment多人版不同，本文不代表正式環境已具備功能。

## 行為

- 僅可靠NKUST HTTPS 404/405/406文章URL精確關聯；去fragment，保留path/query/host。不以相似標題、列表或RSS GUID合併。
- 公開與私人版本分表；私人owner/email複合FK CASCADE，不依會重用的Announcement ID。GET不寫入，匿名公開歷史不讀session/private資料。所有原文保留，不實體合併。
- 舊內容變更前／新內容寫入後，於既有同步lease同交易留存；任何留存失敗rollback。相鄰相同省略，A→B→A仍留三份。既有資料首次觀察留基準，無法回復更早歷史。
- 版本頁顯示原文、跳脫HTML、原解析、來源與台灣留存時間。日期由原文規則及證據產生；不確定顯示待確認，parser差異不宣稱官方更新。修正／待辦／ICS不被自動更新。
- 每頁20筆及下一頁；本人歷史在重解析後仍可發現。損壞紀錄503不假裝空白，錯owner404，匿名私人頁303，page非法422。

## 已執行驗證

第一輪完整pytest：516 passed,49 skipped,2 warnings,100.71s。新增分頁／精確比對與版本回復、schema metadata合併測試：14 passed,2 warnings,8.06s。
六項Node回歸均exit0：calendar_integration_check、calendar_ics_check、todo_store_check、action_card_store_check、announcement_filter_check、pwa_worker_check。
49 skipped為未配置專用PostgreSQL的可選測試（含本階段2項）；沒有執行正式DB。2項為既有Starlette/httpx/anyio棄用提示。最終審查及回歸結果待補。

瀏覽器使用tests/browser/serve_action_cards.py的一次性SQLite與合成A/B帳號，無真實Gmail或正式憑證。已驗證：私人詳情入口、相關來源分區、11/11公開與11/12私人期限差異、私人留存原文展開、公開11/10→11/11版本變更、公開頁不顯示PRIVATE標記、A登出B後不見A及直接存取A版本拒絕。320/390手機寬度無橫向溢出；Tab後summary焦點outline為solid。截圖phase5-source-history-mobile.jpg存於本對話visualizations。

## Rulings I made

1. 私人比較採同郵件＋可靠canonical URL；沒有可靠URL則只比同位置＋指紋，避免重排的無關公告誤認更新。代價：不可靠URL的版本可能缺少自動差異對照。
2. 本人URL前綴候選先精確驗證才分頁，避免相似前綴擠掉真實匹配。代價：大量相同URL郵件會增加記憶體／讀取成本，日後可加canonical索引。

## 限制

未驗證真實PostgreSQL、實體手機、螢幕閱讀器或正式來源線上更新。只保守支援已辨識文章URL，網址改版／別名／其他來源可能無法關聯；同URL仍不保證內容與資格相同。不含主動通知、自動合併、官方內容fetch或完整HTML公開全文；公開來源僅原來源摘要。版本留存增加資料量，沒有自動保留期限或清理；刪帳號清除本人線上版本，備份沿原政策。來源不可靠或期限衝突時由使用者核對原文。
