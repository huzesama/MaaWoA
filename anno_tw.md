# 📰 動態

如果你是付費購買本程式，請立即退款並舉報。此專案是免費、開源的。

## 💻 解析度

- 本專案以 1280x720 為測試基準，理論上可適配市面上主流解析度。如遇到辨識問題，請優先更新 MaaWoA，其次將解析度調整為 1280x720。Android 端請在後台解析度模式選擇 16:9。

## 📱 Android 端後台模式解析度

1. 在停止任務後切換解析度再開始任務，可能會因為快取遺留問題導致辨識失敗。快取依賴 Agent 服務，Agent 只有在啟動 MaaWoA 時才會進行初始化。
2. 切換後台模式解析度後，應先關閉 MaaWoA 及後台處理程序，然後重新啟動。

## 🍎 iOS 控制器（試驗）

- 內建 xdb 用戶端 SDK 為 1.6.1。iOS 連線與 Toolkit 裝置探索要求 xdb Server 1.6.0 或更新版本。用戶端在建連時會檢查執行中的 Server 版本，舊版本或無法辨識的版本會提示升級。
- 桌面端請先依照 [XDeviceBridge 安裝說明](https://github.com/scrctl/XDeviceBridge/blob/main/docs/INSTALL_zh.md) 安裝對應系統與架構的完整執行包，可從 [GitHub Releases](https://github.com/scrctl/XDeviceBridge/releases) 取得。

## 🖥 桌面端前景控制器注意事項與常見問題

1. 前景控制器在執行過程中會完全佔用前景，此時手動操作會干擾指令碼正常執行，不建議同時開啟其他軟體。
2. 截圖功能是直接截取目前前景視窗的畫面，因此截圖中不能出現任何遮擋物，例如幀率顯示、廣告彈出視窗、Windows 未啟用浮水印等，否則會影響辨識。

## 🖥 桌面端後台控制器注意事項與常見問題

- 後台控制器在執行過程可完全後台操作，不會搶奪滑鼠控制權，但需要目標程式支援，並且後台控制器有被擷取操作的可能。

## ⚖️ 授權

- 本軟體的使用需遵守 [GNU Affero General Public License v3.0 (AGPL-3.0)](https://github.com/huzesama/MaaWoA/blob/main/LICENSE)

## ☕ 請我們喝咖啡

如果 MaaWoA 幫你省下了不少時間，不妨[請開發者喝杯咖啡](https://ifdian.net/a/venmzvi)？你的支持是我們持續更新的最大動力！💖
