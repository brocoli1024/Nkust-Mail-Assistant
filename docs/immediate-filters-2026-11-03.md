# 2026-11-03 恢復即時篩選

原因：11月2日將「操作一致」解讀為下拉選單也必須按搜尋，違反使用者原本要求的選完就跳轉。撤回這項互動設計，保留其他第1～5項UX改良。

現行：公開公告分類及對象的change直接requestSubmit，關鍵字可Enter或按搜尋；同一GET表單保留其他條件並回第1頁，無JavaScript時仍可用搜尋按鈕。移除data-explicit-submit例外並更新asset版本，避免舊腳本沿用手動行為。日期、待辦、來源與私人資料流程不變，無schema/OAuth/權限或付費服務變動。

驗證：先改驗收重現0!=2及錯誤表單屬性，再恢復即時change事件。10項Node全退出碼0；完整獨立PostgreSQL18.6為614passed、0skipped、2個既有套件棄用警告，172.75s、SUITE_EXIT0，測試庫已停止。README已改為正確互動說明，11月2日紀錄加上已撤回註記而保留歷史事實。

正式產品b856cbf40a4bc8e31e1992abd84b6e7fd5d66135，Render部署dep-dbkji00u01pc73dfl85g：2026-11-03 09:29:36台灣時間開始、耗時1m36s；09:30:48 PREFLIGHT_OK、09:31:07啟動完成、09:31:13 Live。schema0009、Free方案不變。

正式站驗收：只填MOPCON再選分類活動，未按搜尋即得到q=MOPCON&audience=all&category=活動且共1則；只改對象student，再次自動跳轉為q=MOPCON&audience=student&category=活動且共1則。全程沒有按搜尋，其他條件均保留。新提示及資源版本instant-2已確認，未寫正式待辦/修正或送出報名表單。截圖immediate-filter-live-20261103.png保存於本對話visualizations。管理頁已關閉，保留公開清單。文件提交晚於產品部署，不宣稱文件HEAD已部署。
