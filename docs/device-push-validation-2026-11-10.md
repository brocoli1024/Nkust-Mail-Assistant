# 裝置推播與主畫面引導驗收（2026-11-10）

狀態：本機建置與獨立 PostgreSQL 已完成；正式環境已部署 fed4ca9／schema0011，原公告與待辦回歸可用。新推播尚未啟用，未聲稱真實裝置已收到通知。

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
| Render | 已登入，既有Free服務，Live fed4ca9；Hobby工作區僅1服務，免費時數8.77/750，未付費升級 |
| Cloudflare | 本人已登入，Workers Free $0，無既有應用，當日請求0/100000；已建立 nkust-deadline-push，固定用途程式16cd4c6c已發布；尚無cron |
| Neon | 原專案Free、PostgreSQL18、新加坡、production、6小時歷史；舊手動快照仍保留 |
| 新備份／還原 | 免費快照名額已滿，保留舊快照；已建立同專案備份與還原演練分支，見下方 |
| 新正式祕密 | 尚未設定；由本人使用互動工具產生、輸入及提交 |

待完成：本人設定新祕密及必要當下啟用確認、真實Cloudflare cron兩輪、桌面／Android／iPhone主畫面實測。iPhone關閉網頁後接收、拒絕／撤銷、取消及點擊回公告均未實機驗收。

不因服務accepted、合成介面PASS或安裝引導存在就宣稱裝置送達或整體上線完成。操作次序與限制見[維運文件](device-push-operations.md)。

## 備份與還原演練（正式專案隔離分支）

- 備份 push-pre0011-20261110：br-summer-river-az0m4c40，由 production br-frosty-term-azcuok6j 建立完整資料／schema，同專案且未接應用，保留既有舊快照與預設分支。
- 從備份建立 push-restorecheck-20261110：br-muddy-thunder-azc0z6w9。升級前 schema0010 與原資料彙總一致。
- 只在還原演練分支執行凍結 SQL，成功提交0011；原有使用者／郵件／私人公告／公開公告彙總未變，nkust_public_sync 無 push_devices SELECT 權限。未在文件紀錄私人資料筆數或憑證。
- production 已套用同一0011交易，升級後彙總一致且公開同步角色拒存取推播表；兩個隔離分支保留，不自動刪除資料或升級付費方案。

## 正式網站發布檢查

- 將 fed4ca9 快進推到既有 codex/web-deployment，並推送相容回復分支；main未修改。
- 發布前進入設定核對，發現原 Auto-Deploy 實際為 On Commit，先保存為 Off，再推送。先前只見 Manual Deploy 按鈕不能證明自動部署關閉。
- production0011驗證後，Render手動指定fed4ca9發布，已實際看到Live及正式網站新版。
- 公開清單、公務清單（20則）、待辦讀取、加入主畫面對話框可用；裝置提醒明確顯示尚未開放，未要求通知權限。
- 原來源頁顯示更新過期；GitHub既有第41輪在新版發布前已因OFFICE_DISCOVERY_TRIGGER_UNCONFIRMED失敗，並有單篇PUBLIC_ARTICLE_BODY警告。已使用既有工作流程重跑失敗job核對0011相容，不改原排程或權限。attempt2實際成功：feed／articles／office_mail／discovery退出碼均0。discovery保留有界待處理警告，未誤列全部已收完。
- Render六項名稱與非祕密false／subject已備好；Cloudflare同名Secret欄位已備好。新值由本人輸入、儲存；尚未收到完成回覆，不啟用旗標或cron。

## 啟用設定檢查續作

- 本人已確認Render／Cloudflare儲存新祕密，且另於啟用當下同意flag與cron。未將任何值寫入此文件。
- 啟用操作後的API仍false；核對發現原旗標未持久更新。使用已顯示的非祕密欄精準改true並驗保存後重新部署。
- 啟用部署dep-dbpb7ndbedkc7388mmpg啟動失敗：config.py第28行PUSH_CONFIGURATION_INVALID，原因為Subject帶有變數名稱前綴。Subject已更正為本站HTTPS網址。既有健康版本仍提供公告，未啟用cron。
- 其他祕密可能有同樣的整行貼上格式；已交本人確認四個Render憑證及Cloudflare相同trigger只填等號右側值。未讀取、記錄或代改秘密。須等本人確認再部署與觀察真cron。

- 本人回覆格式確認後，重新部署仍在公私鑰驗證失敗。只顯示可公開公鑰檢查，確認伺服器儲存值仍含NKUST_PUSH_VAPID_PUBLIC_KEY=前綴；未讀取私鑰。已備妥Render Edit，交本人修正Value並明確按Save only。Cloudflare原Unsaved changes已由本人Save，已確認消失且Secret存在。cron仍未啟用，API仍false；不得宣稱正式推播完成。

## 正式啟用成功（後續驗收仍進行）

- 本人完成Render修正並按Save only；重新載入伺服器設定後，公鑰不含前綴、base64url格式正確。私鑰沒有被顯示或記錄。
- 重新部署0cd04f4於台灣時間2026-11-10 14:24:17回報Your service is live；公開/api/push/config實際HTTP200、enabled=true且有公鑰。公私鑰已通過伺服器配對驗證。
- Cloudflare重新載入確認已存在每5分鐘規則（不是只有編輯草稿）；保留既有單一規則，不重複新增。正在核對真實scheduled結果，尚未列兩輪通過。
- 已請本人進行iPhone主畫面App通知測試。測試通知的正確點擊入口為/todos；真正截止提醒才進來源詳情。尚未收到實機結果。
