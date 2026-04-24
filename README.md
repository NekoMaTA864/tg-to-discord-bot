# ImageBOT Pro - 跨平台自動化圖文管家

這是一個用 Python 寫的簡單機器人，用來自動從 Telegram 轉發訊息到 Discord。主要是為了方便管理跨平台的圖文內容。

## 主要功能

- 自動監聽 Telegram 頻道的新訊息，包括文字、圖片和影片。
- 解析訊息中的標籤（如 #Character, #Artist, #Material），並自動分類發送到對應的 Discord 頻道。
- 支援繁體中文轉換。
- 簡單的圖形介面，方便操作。
- 處理大檔案和批次發送。

## 使用的技術

- Python 3.10+
- 主要套件：Telethon, discord.py, customtkinter, opencc, python-dotenv
- 環境管理：Conda 或 pip

## 如何使用

### 1. 準備環境
安裝 Python 3.10 或以上版本。建議用 Conda 建立虛擬環境：

```bash
conda create -n imagebot python=3.10 -y
conda activate imagebot
```

### 2. 安裝套件
```bash
pip install -r requirements.txt
```

### 3. 設定環境變數
複製 `.env.example` 成 `.env`，然後填入你的 API 資訊：

```env
TG_API_ID=你的_TG_API_ID
TG_API_HASH=你的_TG_API_HASH
TG_SOURCE_CHANNEL=欲監聽的頻道ID或名稱
DISCORD_BOT_TOKEN=你的_Discord_Bot_Token
DISCORD_SERVER_ID=你的_Discord_伺服器ID
```

**注意：** 不要把 `.env` 檔案上傳到公開地方！

### 4. 啟動程式
執行：

```bash
python main.py
```

開啟介面後，按「啟動系統」開始監聽。

## 注意事項

- 這是個人使用的簡單工具，不是商業產品。
- 使用前請確保你有 Telegram 和 Discord 的 API 權限。
- 如果有問題，可以檢查 API 設定或網路連線。
