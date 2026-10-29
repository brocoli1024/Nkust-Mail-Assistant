# 第三階段驗證紀錄（2026-10-29）

狀態：隔離工作區實作、合成資料驗證及獨立審查修正已完成，未部署、未執行正式 migration／OAuth 變更／新付費服務。正式環境功能與 main、網站分支、本機工作區分開判斷。

## 現在可用

公開／私人／demo 詳情自行加入待辦，系統辨識不會自動建立。完成／重新開啟／稍後／移除，保留加入時資訊及來源。未知日期不升級為截止，適用對象不當成資格。待辦不是公告原始欄位，移除不改公告與修正。

公開保存於原 IndexedDB v2 的 publicTodos，保留 v1 publicActionCards；共用裝置可見，清除瀏覽器資料會遺失。私人保存於 owner-bound private_todos（migration0008），複合 Email owner FK／Google subject／User 鎖／CAS；不進持久瀏覽器儲存。demo記憶體重載清空。移除採保留版本與快照的墓碑避免 ABA，清單隱藏但不是刪除全部保存資料，README與隱私已揭露。

首頁先呈現裝置待辦，私人總覽先呈現帳號待辦；兩區不自動匯入。截止排序、今天起七日內／逾期提示。稍後固定明天09:00台灣時間，按前顯示確切年月日時間；到期重開頁或每分鐘重新計算／私人頁重整，不發推播。截止早於稍後日期提示風險。

## 自動測試

Task1 缺模組 RED→33 passed；Task2 缺表單7 RED→相關57 passed；Task3 Node缺模組／損壞讀取RED→GREEN，公開相關38 passed。測試涵蓋台灣跨日／年底、未知截止、明確加入、保存與狀態、移除重加防ABA、來源與修正版本、重解析、Google身分／owner／CASCADE、雙寫入競爭、HTTP CSRF／Origin:null／跨站／格式／容量／錯owner、503不當空白。

首輪完整 pytest：497 passed、47 skipped、2 warnings、125.59秒（exit0）；四項 Node（todo/store/filter/SW）及 diff --check 通過。47個略過為專用 PostgreSQL 未設定，新增4個待辦合約亦提供同一測試庫入口，但未實測，不以SQLite代替PostgreSQL驗收。兩項為既有測試客戶端棄用警告。

## 真實瀏覽器（合成資料）

只啟動 loopback 臨時 SQLite／FakeGoogle app。獨立隨機測試DB的原生IDB harness PASS：v1→v2保留修正、重開保存、雙寫入只一方成功、quota／abort故障注入不改先前值、稍後到期投影回active、移除重加。未填滿真實裝置儲存空間，測試只清除自己的隨機DB。

公開詳情加入→重載→裝置清單仍存在；兩分頁同版本，一方完成，另一方顯示衝突且不覆寫，重新讀取可恢復。示範加入後reload回未加入。私人A正常表單加入／完成→正常登出→B的完成清單無A內容；私人頁不載入兩種裝置儲存腳本。

公開及私人待辦在320／390px無水平溢出，Tab焦點solid。手機實測抓到暗色section套用淺色文字至紙色卡片，已用現有ink-muted修正並重新檢查；沒有額外配色。截圖 phase3-todos-mobile.jpg 僅含合成公告。

限制：未實測實體手機、其他瀏覽器、螢幕閱讀器、瀏覽器完全停用JS或真實隔夜等待。正常私人HTML表單實際通過；稍後到期以純日期測試及原生harness投影驗證，不宣稱真實等待到隔天。PostgreSQL及修正／同步／刪帳號真實交錯仍需發布前隔離驗收。沒有跨裝置同步，沒有離線完整公告快取。

## 獨立審查

一次fresh全範圍唯讀審查：0 Critical、2 Important、0 Minor。兩項重要問題已在一輪修正補RED→GREEN：

1. SQLite無時區稍後值輸出HTML前正規化UTC；clock明確解析offset，僅對尚在稍後狀態的marker判斷，不漏掉頁面渲染途中到期。測試確認服務值、實際HTML含+00:00，以及clock在到期前／當下的判斷。
2. 跨台灣午夜後不能把畫面顯示的稍後時間悄悄延一天。私人表單提交顯示目標，由server核對；public/demo按鈕捕捉顯示目標，跨日拒絕並重新確認。實際私人／公開正常稍後操作修正後重驗，原生harness再次PASS。

本階段無延期小項。審查set-aside四項裁定：部署／正式遷移維持不執行（代價是仍需獨立發布操作）；PostgreSQL沒有專用庫，47個skip明列（代價是PG鎖定仍需發布前驗收）；手機由本機父流程實測320/390與焦點／對比，不宣稱實體機或螢幕閱讀器（代價是特定裝置仍可能有問題）；暫缺文件已更新README／privacy／spec／本紀錄及移除墓碑保存說明（代價是後續更動仍需同步文件）。

第四／第五階段仍保留設計：選擇活動或截止、確認日期後下載 .ics，全天／Asia/Taipei／來源及僅宣稱下載；跨來源只用可靠URL或ID，保留版本來源及私人原文隔離。不實作Calendar授權、自動相似標題合併或新來源。

最終回歸：**500 passed、47 skipped、2 warnings、141.73秒，exit0**，basetemp=data/audit-cache/phase3-final-suite。四項Node及diff --check均exit0。兩個重要問題無未解決項目，本階段無延期小項；仍保留上述發布驗收限制。已關閉合成QA分頁及本機預覽服務，保留合成截圖。原目錄既有Dashboard／字型／readiness變更未動，僅保留本機工作區與提交。
