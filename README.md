# ImageBOT Pro - 跨平台自動化圖文管家 

這是一個基於 Python 開發的自動化轉傳機器人。主要為了解決資訊焦慮與跨平台管理的痛點，能夠實時監聽 Telegram 特定頻道的圖文訊息，並根據自訂規則（如繪師名稱、作品標籤），自動分類並無縫轉發至 Discord 指定頻道。

## ✨ 核心特色 (Features)

* **自動化監聽與下載：** 實時擷取 Telegram 指定頻道的文字、圖片與影片。
* **智慧標籤解析：** 自動辨識 `#Character`, `#Artist`, `#Material` 等標籤，並進行繁體中文在地化修正。
* **精準頻道分流：** 依據解析出的標籤，自動對應並轉發至 Discord 中對應的專屬頻道。
* **大檔案防呆機制：** 自動偵測 Discord 25MB 的檔案限制，超過限制的檔案會安全保留於本地端並發送警告。
* **批次發送優化：** 處理大量相簿媒體時，自動進行 10 張為一組的批次發送，避免洗版與傳輸失敗。
* **圖形化控制介面 (GUI)：** 提供簡潔的控制面板，可即時查看暫存空間、運行日誌，並具備手動修正最後一則訊息的功能。

## 🛠️ 技術棧 (Tech Stack)

* **語言:** Python 3.10+
* **核心套件:**
  * `Telethon` (Telegram API 串接)
  * `discord.py` (Discord Webhook/Bot 串接)
  * `customtkinter` (GUI 介面開發)
  * `opencc-python-reimplemented` (繁簡轉換)
  * `python-dotenv` (環境變數管理)
* **環境管理:** Conda / pip

## 🚀 快速開始 (Quick Start)

### 1. 環境準備
確保你的系統已安裝 Python 3.10 或以上版本。建議使用 Conda 建立獨立的虛擬環境：

```bash
conda create -n imagebot python=3.10 -y
conda activate imagebot
```

### 2. 安裝依賴套件
```bash
pip install -r requirements.txt
```

### 3. 環境變數設定
請複製專案中的 `.env.example` 檔案，並將其重新命名為 `.env`。接著填入你專屬的 API 資訊：

```env
TG_API_ID=你的_TG_API_ID
TG_API_HASH=你的_TG_API_HASH
TG_SOURCE_CHANNEL=欲監聽的頻道ID或名稱
DISCORD_BOT_TOKEN=你的_Discord_Bot_Token
DISCORD_SERVER_ID=你的_Discord_伺服器ID
```

**注意：** 絕對不要將填妥的 `.env` 檔案上傳至任何公開平台！

### 4. 啟動系統
在終端機中執行主程式：

```bash
python main.py
```

啟動後將開啟控制面板，點擊「🚀 啟動系統」即可開始監聽。

## 📖 使用說明 (Usage)

### GUI 介面操作
- **啟動系統：** 點擊「🚀 啟動系統」按鈕開始監聽 Telegram 頻道。
- **修正訊息：** 在編輯框輸入新文字，點擊「✏️ 修正最後一則」來編輯 Discord 上的最後一則訊息。
- **清理暫存：** 點擊「🧹 清理暫存」來清空 `images/` 和 `videos/` 資料夾。

### 標籤解析規則
程式會自動解析訊息中的標籤：
- `#Character`：角色名稱
- `#Artist`：繪師名稱
- `#Material`：作品標籤

並根據內建映射表將標籤轉換為對應的 Discord 頻道名稱。

## 🔧 故障排除 (Troubleshooting)

- **Telegram 連線失敗：** 確認 API ID 和 Hash 正確，並確保帳號有權限存取目標頻道。
- **Discord 發送失敗：** 檢查 Bot Token 和 Server ID 是否正確，Bot 是否有發送訊息權限。
- **檔案過大：** Discord 免費版限制 25MB，超過的檔案會保留本地。
- **編輯訊息失敗：** 確保有最近的訊息記錄，且 Bot 有編輯權限。
