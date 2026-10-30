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
49 skipped為未配置專用PostgreSQL的可選測試（含本階段2項）；沒有執行正式DB。2項為既有Starlette/httpx/anyio棄用提示。第二輪完整pytest：518 passed,49 skipped,2 warnings,163.91s，含追加分頁／精確比對案例。獨立審查首次因使用額度中斷，依使用者接續指示由同一審查者恢復，已完成：Critical0、Important0、Minor1，結論可保留／整合；沒有再派第二次審查。

瀏覽器使用tests/browser/serve_action_cards.py的一次性SQLite與合成A/B帳號，無真實Gmail或正式憑證。已驗證：私人詳情入口、相關來源分區、11/11公開與11/12私人期限差異、私人留存原文展開、公開11/10→11/11版本變更、公開頁不顯示PRIVATE標記、A登出B後不見A及直接存取A版本拒絕。320/390手機寬度無橫向溢出；Tab後summary焦點outline為solid。截圖phase5-source-history-mobile.jpg存於本對話visualizations。另以一次性庫追加21版本，實際點擊公開／私人「下一頁」均可找到首次留存；公開第二頁仍顯示舊新期限。臨時分頁已關閉、尺寸已還原、合成服務已停止。

## Rulings I made

1. 私人比較採同郵件＋可靠canonical URL；沒有可靠URL則只比同位置＋指紋，避免重排的無關公告誤認更新。代價：不可靠URL的版本可能缺少自動差異對照。
2. 本人URL前綴候選先精確驗證才分頁，避免相似前綴擠掉真實匹配。代價：大量相同URL郵件會增加記憶體／讀取成本，日後可加canonical索引。

3. 審查另提出大量同網址郵件的查詢成本：維持第2項設計，索引優化延期；代價是大郵件量仍可能增加讀取／記憶體成本。
4. 審查未判斷真實PostgreSQL及正式環境：不以SQLite／離線編譯代替實機成功，不操作禁止的正式環境；代價是部署前仍需專用PostgreSQL驗收。

## 最終審查與 Deferred minors

同一fresh reviewer檢查e7eaf67..12e66ed並以記憶體SQLite獨立重現網址邊界；初次使用額度中斷後由同一審查者接續。Critical／Important均無，Minor1。執行者依實際影響維持Minor：明列HTTPS預設埠`:443`的私人URL，雖被official_identity正規化為相同URL，仍被source_views.py的原始URL前綴候選查詢漏掉。這只造成少數相關來源漏列，不刪除原文、不跨帳號、沒有資料外洩；可在我的公告／來源留存查原資料。依inline計畫Minor延期，未進fix pass。後續建議讓候選查詢涵蓋接受的正規化形式，並加入雙向比對測試。

無其他延期minor。所有rulings及審查未判斷項目均已列於上節。原工作區既有dashboard/CSS/文件/fonts修改未觸碰；本階段僅保留本機isolated worktree提交。

## 限制

未驗證真實PostgreSQL、實體手機、螢幕閱讀器或正式來源線上更新。只保守支援已辨識文章URL，網址改版／別名／其他來源可能無法關聯；同URL仍不保證內容與資格相同。不含主動通知、自動合併、官方內容fetch或完整HTML公開全文；公開來源僅原來源摘要。版本留存增加資料量，沒有自動保留期限或清理；刪帳號清除本人線上版本，備份沿原政策。來源不可靠或期限衝突時由使用者核對原文。
