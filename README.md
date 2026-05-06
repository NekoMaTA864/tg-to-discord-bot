# ImageBOT - 跨平台自動化圖文管家

一個基於 Python 的跨平台自動化系統，透過 API 串接與非同步處理 (Async Programming)，實現 Telegram 到 Discord 的媒體同步與分類流程。本系統具備智慧標籤解析、自動化媒體壓縮以及雲端物件儲存整合能力，專為處理高併發與大容量媒體分發而設計。

---

## 專案概述 (Overview)

本專案旨在解決多平台內容分散與管理不便的問題，透過自動化流程建立「集中式內容管理工作流」。

**核心能力：**
- **API Integration：** Telegram 與 Discord 雙向 API 深度串接。
- **Workflow Automation：** 媒體下載、標籤解析、頻道路由自動化。
- **Async Programming：** 採用非同步架構，提升高併發情境下的系統穩定度與吞吐量。
- **Media Processing：** 內建 FFmpeg 硬體加速，智慧評估並壓縮過大媒體檔。
- **Cloud Integration：** 整合 Cloudflare R2 雲端儲存，突破社群平台檔案大小限制。

---

## 系統流程 (System Workflow)

1. **偵測監聽：** 實時監聽 Telegram 指定來源頻道的新進訊息。
2. **媒體擷取：** 智慧判斷單一媒體或相簿集，建立緩衝區收集完整檔案後進行下載。
3. **標籤解析與路由：** 使用正則表達式萃取標籤，並比對 JSON 設定檔，決定最終分發的目標頻道。
4. **在地化處理：** 結合 OpenCC 與自訂字典進行繁簡轉換與專有名詞統一。
5. **資源分流與處理：** 依據檔案大小進行本地壓縮，或啟動多執行緒上傳至雲端儲存空間。
6. **內容分發：** 非同步發佈格式化後的圖文與媒體連結至 Discord。

---

## 核心功能與工程亮點 (Engineering Highlights)

- **智慧相簿合併機制：** 解決 Telegram 相簿為多重獨立訊息的問題，透過記憶體緩衝區與延遲處理，將關聯訊息整合為 Discord 的單次批次發送。
- **雙軌媒體處理策略：**
  - **自動壓縮：** 整合 FFmpeg，優先調用 AMD GPU (h264_amf) 進行硬體加速壓縮，若環境不支援則無縫切換至 CPU 極速編碼模式。
  - **雲端分流：** 超過 Discord 上傳限制的超大型檔案，自動透過 boto3 (S3 相容 API) 以 Multipart 方式平行上傳至 Cloudflare R2，並回傳直連網址。
- **設定與機密分離架構：** 嚴格區分機敏資料與邏輯配置。金鑰統一由 `.env` 管理，而頻道映射、在地化詞彙等業務邏輯則抽離至 `config.json`，提升系統擴充性與開源安全性。
- **現代化控制面板：** 基於 customtkinter 開發獨立 GUI，提供即時日誌監控與儲存空間管理功能，並支援系統匣 (System Tray) 背景常駐。

---

## 技術架構 (Tech Stack)

- **核心語言：** Python 3.10
- **第三方服務與 API：**
  - `Telethon` (Telegram API)
  - `discord.py` (Discord API)
  - `boto3` (Cloudflare R2 / S3 相容物件儲存 API)
- **資料處理與介面：**
  - `asyncio` (非同步任務與子進程管理)
  - `customtkinter` (圖形化控制介面)
  - `opencc-python-reimplemented` (文字繁簡轉換)
- **外部依賴：**
  - `FFmpeg` / `FFprobe` (多媒體分析與轉碼)

---

## 開發挑戰與解決方案 (Challenges & Solutions)

### 1. 跨平台資料結構差異
- **問題：** Telegram 傳送多圖相簿時，底層為多條帶有相同 `grouped_id` 的獨立訊息，容易導致 Discord 端收到破碎的單圖推播。
- **解法：** 實作基於 `grouped_id` 的快取機制。當接收到相簿首張圖片時啟動 5 秒等待視窗，攔截後續關聯媒體，待收集齊全後再行打包下載與轉發。

### 2. Discord API 上傳限制 (Rate Limit & File Size)
- **問題：** Discord 頻道有嚴格的 25MB 檔案限制，且頻繁請求容易觸發 429 Too Many Requests。
- **解法：** 導入動態檔案大小評估機制。系統會先行偵測伺服器加成等級 (Premium Tier) 決定上傳上限。針對過大檔案實作 FFmpeg 壓縮降級，若仍超出限制則分流至 R2 雲端。

### 3. 大型檔案上傳的網路阻塞
- **問題：** 單線程上傳數百 MB 的影片至雲端時，容易因網路波動導致 Timeout 或阻塞主程式。
- **解法：** 採用 `boto3` 的 `TransferConfig` 實作多執行緒分塊上傳 (Multipart Upload)，設定 8MB 為單一區塊並啟用高併發連線，大幅提升傳輸穩定度。

---

## 快速啟動 (Quick Start)

### 1. 建立環境
```bash
conda create -n imagebot python=3.10 -y
conda activate imagebot
```

### 2. 安裝依賴
```bash
pip install -r requirements.txt
```

### 3. 安裝外部工具
請確保系統已安裝 FFmpeg，並將其加入系統環境變數 (PATH)。

### 4. 設定環境變數
複製範例檔案並填入您的真實資訊：
- 複製 .env.example 為 .env，填入 Telegram/Discord API 金鑰與 R2 憑證。
- 複製 config.example.json 為 config.json，根據需求配置頻道路由與標籤映射。

### 5.啟動系統
```bash
python main.py
```

## 開發中與未來優化目標 (Work in Progress & Future Roadmap)
### 進行中的架構升級 (WIP)

- FFmpeg 媒體壓縮與轉檔
  - 已完成基本流程
  - 持續優化穩定性與畫質

- Cloudflare R2 + Workers 串流整合
  - 已能生成播放器連結
  - 大型檔案仍需進一步優化

## 未來規劃 (Planned)

- 導入 SQLite 建立輕量化本地資料庫，用於持久化儲存轉發紀錄與錯誤重試佇列。
- 支援更細緻的 FFmpeg 參數自訂功能 (例如動態解析度縮放)。
- 將核心邏輯打包為 Docker Image，便於伺服器端無頭 (Headless) 部署。
