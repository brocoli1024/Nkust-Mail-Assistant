# 裝置推播與主畫面引導驗收（2026-11-10）

狀態：本機建置與獨立 PostgreSQL 已完成；正式環境仍是 afa0f03／schema0010。新推播尚未啟用，未聲稱真實裝置已收到通知。

## 已完成

- 實作基礎與審查修正 commit：45f9c7d。核准規格／計畫日期2026-11-08，跨日續作2026-11-10。
- 最終完整獨立 PostgreSQL：817 passed、0 skipped，139.96秒。兩個既有 Starlette／anyio 相依套件棄用警告；無新失敗。測試目標本機127.0.0.1:55439、全新合成 schema、非管理員 owner，另有受限 nkust_public_sync 角色；未連正式 Neon 執行開發測試。
- 19項 Node 檢查全部通過；涵蓋既有分類／搜尋、公開閱讀、行事曆、校區、待辦及新 push／安裝流程。
- Chrome 原生 IndexedDB：v2→v3保留、quota／abort一起撤回、未 opt-in 零上傳、離線取消、晚到建立回覆後取消確實同步、busy期間第二筆不漏送、舊epoch回覆不清新裝置、遺失取消回覆後重設仍保留待辦，均實際觀察 PASS。
- 本機合成提醒介面：確認截止與保存範圍後才啟用，前一天09:00、服務確認與最少資料同步 PASS；沒有要求真實通知權限或送實際推播。手機390×844主畫面引導已檢查並修正按鈕對比。

獨立審查範圍58d4f8a..5caaf1d，提出1項Critical、10項Important與1項Minor。已逐項補重現測試及修正：真實 serializer、epoch寫入、取消競爭、測試連線覆寫、重設恢復、端點別名、既有修正baseline、測試容量／重送、source_ref型別、busy假成功、日期保留與註解。817項是修正後結果；沒有把原審查的「不宜合併」假稱為再次獨立審查通過。

## 回復與來源排程

- 相容回復 d4a8383：獨立 PostgreSQL smoke PASS；schema0011下公開／公務／待辦可讀、私人登入與隔離正常、新push路由404。
- 原生瀏覽器回復驗收 PASS：回復程式可讀IDBv3待辦及修正歷史，資料保留且仍原子排入取消；不以刪庫處理版本問題。SW保留安全處理以銜接已提交訊息。
- 遠端 main=9784e02、codex/web-deployment=b11092f（發布前讀取）；每小時17分的既有工作流程checkout部署分支。新增公開CLI0010／0011銜接測試通過，不更改原排程或管理者Gmail整合。

## 正式啟用前查核

| 項目 | 實際狀態 |
|---|---|
| Render | 已登入，既有Free服務，Live仍afa0f03；Hobby工作區僅1服務，免費時數8.77/750，未付費升級 |
| Cloudflare | 本人已登入，Workers Free $0，無既有應用，當日請求0/100000；尚未建立此排程 |
| Neon | 原專案Free、PostgreSQL18、新加坡、production、6小時歷史；舊手動快照仍保留 |
| 新備份／還原 | 免費快照名額已滿，保留舊快照；已建立同專案備份與還原演練分支，見下方 |
| 新正式祕密 | 尚未設定；由本人使用互動工具產生、輸入及提交 |

待完成：production 0011加法遷移、flag關閉部署與原功能回歸、本人設定新祕密及必要當下啟用確認、真實Cloudflare cron兩輪、桌面／Android／iPhone主畫面實測。iPhone關閉網頁後接收、拒絕／撤銷、取消及點擊回公告均未實機驗收。

不因服務accepted、合成介面PASS或安裝引導存在就宣稱裝置送達或整體上線完成。操作次序與限制見[維運文件](device-push-operations.md)。

## 備份與還原演練（正式專案隔離分支）

- 備份 push-pre0011-20261110：br-summer-river-az0m4c40，由 production br-frosty-term-azcuok6j 建立完整資料／schema，同專案且未接應用，保留既有舊快照與預設分支。
- 從備份建立 push-restorecheck-20261110：br-muddy-thunder-azc0z6w9。升級前 schema0010 與原資料彙總一致。
- 只在還原演練分支執行凍結 SQL，成功提交0011；原有使用者／郵件／私人公告／公開公告彙總未變，nkust_public_sync 無 push_devices SELECT 權限。未在文件紀錄私人資料筆數或憑證。
- production 尚未升級；兩個隔離分支保留，不自動刪除資料或升級付費方案。
