# logic.py
import discord, time
import sys, re, os, asyncio
from telethon import TelegramClient, events
from opencc import OpenCC
from dotenv import load_dotenv

# 載入 .env 檔案裡面的環境變數
load_dotenv()

# --- 基礎配置 (從session.env讀取) ---
# 注意：API_ID 和 SERVER_ID 需要用 int() 轉換成整數
TG_API_ID = int(os.getenv('TG_API_ID', 0))
TG_API_HASH = os.getenv('TG_API_HASH')
TG_SOURCE_CHANNEL = os.getenv('TG_SOURCE_CHANNEL')

# 如果 TG_SOURCE_CHANNEL 是一串數字的 ID (例如 -100123456789)，也需要轉整數
if TG_SOURCE_CHANNEL.lstrip('-').isdigit():
    TG_SOURCE_CHANNEL = int(TG_SOURCE_CHANNEL)

DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
DISCORD_SERVER_ID = int(os.getenv('DISCORD_SERVER_ID', 0))

# 1. 在地化字詞修正表 (可隨時擴充)
WORD_REPLACEMENTS = {
    "视频": "影片", "质量": "品質", "账号": "帳號",
    "绝区零": "絕區零", "崩坏": "崩壞", "星穹铁道": "星穹鐵道"
}

# 2. 作品別名映射 (標籤 -> Discord 頻道名稱)
RAW_SERIES_DATA = {
    "妮姬": ["nikke", "victorygoddess", "勝利女神"],
    "zzz": ["zzz", "zenlesszonezero", "絕區零"],
    "鐵道": ["Honkai_StarRail", "スターレイル", "星穹铁道", "星穹鐵道"],
    "檔案": ["bluearchive", "ba", "蔚藍檔案", "碧藍檔案", "ブルーアーカイブ"],
    "符合舟禮": ["arknight", "明日方舟"],
    "大奶航線": ["碧蓝航线", "アズールレーン"],
    "大鳴王朝": ["WutheringWaves", "鸣潮"],
    "原批": ["GenshinImpact", "原神"],
}
# 自動生成扁平化映射表，並將 key 轉為小寫以利比對
SERIES_MAPPING = {alias.lower(): real_name for real_name, aliases in RAW_SERIES_DATA.items() for alias in aliases}

# --- 全域記憶體 ---
last_captured_text = ""
last_text_time = 0

# --- 全域工具與變數 ---
cc = OpenCC('s2twp') 
discord_client = discord.Client(intents=discord.Intents.default())

if getattr(sys, 'frozen', False):
    # 如果是打包後的 .exe
    base_path = os.path.dirname(sys.executable)
else:
    # 如果是平常在 VS Code 執行
    base_path = os.path.dirname(os.path.abspath(__file__))

# 強制指向 .exe 旁邊的 session 檔案
session_name = os.path.join(base_path, 'bot_session') 
tg_client = TelegramClient('bot_session', TG_API_ID, TG_API_HASH)

album_cache = {}  
album_tasks = {}  
log_func = print  
last_msg = None   # 儲存最後一個發出的 Discord 訊息物件

def localize(text):
    """將文字簡轉繁並根據 WORD_REPLACEMENTS 修正慣用語"""
    if not text: return ""
    converted = cc.convert(text)
    for s, t in WORD_REPLACEMENTS.items():
        converted = converted.replace(s, t)
    return converted

def prog_cb(current, total):
    """回報下載進度給 UI"""
    if current == total:
        log_func(f"  └─ 📥 媒體下載完成 (100%)")

async def process_and_send(raw_text, file_paths):
    """處理 Telegram 訊息並發送到 Discord 的核心函數"""
    global last_msg, last_captured_text, last_text_time
    guild = discord_client.get_guild(DISCORD_SERVER_ID)
    if not guild: return

    current_time = time.time()

    # 1. 記憶體邏輯：處理大量上傳時「沒文字」的圖片
    if raw_text.strip():
        last_captured_text = raw_text
        last_text_time = current_time
    elif (current_time - last_text_time) < 30: # 大量上傳建議放寬到 15 秒
        raw_text = last_captured_text

    # 2. 解析標籤內容
    char_m = re.search(r"Character.*?[:：]\s*(.*)", raw_text, re.IGNORECASE)
    art_m = re.search(r"Artist.*?[:：]\s*(.*)", raw_text, re.IGNORECASE)
    mat_m = re.search(r"Material.*?[:：]\s*(.*)", raw_text, re.IGNORECASE)

    c_tag = localize(char_m.group(1).strip() if char_m else "")
    a_tag = localize(art_m.group(1).strip() if art_m else "")
    m_tag = localize(mat_m.group(1).strip() if mat_m else "")

    # 2. 頻道分流邏輯
    target_channel = None
    # 優先找繪師 (#Artist 內容)
    a_hashes = re.findall(r'#(\w+)', a_tag)
    for t in a_hashes:
        target_channel = discord.utils.get(guild.text_channels, name=t.lower())
        if target_channel: break
    
    # 次要找作品 (別名映射)
    if not target_channel:
        m_hashes = re.findall(r'#(\w+)', m_tag)
        for t in m_hashes:
            dest = SERIES_MAPPING.get(t.lower(), t.lower())
            target_channel = discord.utils.get(guild.text_channels, name=dest)
            if target_channel: break

    # C. 防呆：找不到就進「其他」
    if not target_channel:
        target_channel = discord.utils.get(guild.text_channels, name="其他")

    if target_channel:
        log_func(f"🔍 [解析] 頻道目標: #{target_channel.name}")
        
        # 3. 組合發送文字 (使用 Markdown 程式碼區塊)
        final_list = [t for t in [c_tag, a_tag, m_tag] if t]
        inner = "\n".join(final_list) if final_list else localize(raw_text).strip()
        custom_text = f"```\n{inner}\n```"

        # 4. 準備檔案並檢查大小 (Discord 免費版限制約 25MB)
        ready_files = []
        over_info = ""
        for p in file_paths:
            if os.path.exists(p):
                size = os.path.getsize(p) / (1024*1024)
                if size <= 25:
                    ready_files.append(discord.File(p))
                else:
                    over_info += f"\n⚠️ 檔案過大已保留本地: {os.path.basename(p)} ({size:.1f}MB)"

        # 5. 發送至 Discord 並記住該訊息
        try:
            # 如果連文字都沒有且沒檔案，就不發送
            if not ready_files and not custom_text:
                return

            # 使用 range 迴圈，每次跳 10 個檔案
            for i in range(0, len(ready_files), 10):
                batch = ready_files[i:i+10]
                
                # 只有發送第一批時會帶文字標籤與大檔案警告
                # 如果是第 21 張圖，custom_text 會變為空字串，才不會重複洗版
                content_to_send = (custom_text + over_info) if i == 0 else ""
                
                last_msg = await target_channel.send(content=content_to_send, files=batch)
                
                # 如果有很多組，可以噴個進度
                if len(ready_files) > 10:
                    log_func(f"📦 [批次] 已送達第 {i//10 + 1} 組媒體...")

            log_func(f"✨ [完成] 全數訊息已送達 Discord")

            # --- 第三階段：全部發完後，安全刪除 ---
            await asyncio.sleep(2)
            for p in file_paths:
                try:
                    if os.path.exists(p): os.remove(p)
                except: pass

        except Exception as e:
            log_func(f"💥 [錯誤] Discord 發送失敗: {e}")

async def edit_last_logic(new_text):
    """執行 Discord 上的編輯動作"""
    global last_msg
    if last_msg:
        try:
            # 加上 ``` 使格式整齊
            await last_msg.edit(content=f"```\n{new_text}\n```")
            return True
        except Exception as e:
            return f"編輯失敗: {e}"
    return "找不到最後一則訊息紀錄"

def run_logic(ui_callback):
    """由 main.py 呼叫的啟動進入點"""
    global log_func
    log_func = ui_callback
    os.makedirs("images", exist_ok=True)
    os.makedirs("videos", exist_ok=True)

    @tg_client.on(events.NewMessage(chats=TG_SOURCE_CHANNEL))
    async def handler(event):
        if event.message.media:
            gid = event.message.grouped_id
            log_func(f"🔔 [偵測] 收到媒體訊息 (ID: {event.message.id})")
            save_path = "images/" if event.message.photo else "videos/"
            path = await event.message.download_media(file=save_path, progress_callback=prog_cb)
            
            if gid: # 相簿處理邏輯 (等待 5 秒收齊)
                if gid not in album_cache: album_cache[gid] = {"text": "", "files": []}
                if event.message.text: album_cache[gid]["text"] = event.message.text
                album_cache[gid]["files"].append(path)
                if gid in album_tasks: album_tasks[gid].cancel()
                async def delayed(g_id):
                    await asyncio.sleep(5)
                    if g_id in album_cache:
                        data = album_cache.pop(g_id)
                        await process_and_send(data["text"], data["files"])
                album_tasks[gid] = asyncio.create_task(delayed(gid))
            else: # 單一媒體處理
                await process_and_send(event.message.text or "", [path])

    @discord_client.event
    async def on_ready():
        log_func(f"✅ Discord 機器人已上線: {discord_client.user}")
        try:
            log_func("📡 正在嘗試連線至 Telegram...")
            await tg_client.start()
        
            # 🌟 核心修正：手動讓 TG 認識這個頻道 (手動刷入快取)
            # 這樣下方的監聽器就不會報 ValueError 了
            try:
                await tg_client.get_entity(TG_SOURCE_CHANNEL)
                log_func(f"📢 已成功識別目標頻道 ID: {TG_SOURCE_CHANNEL}")
            except Exception as e:
                log_func(f"⚠️ 無法識別頻道，請確認帳號是否在頻道內: {e}")

            log_func("📡 Telegram 監聽系統已成功啟動！")
        except Exception as e:
            log_func(f"❌ TG 啟動失敗: {e}")

    log_func("🔄 正在啟動系統核心...")
    discord_client.run(DISCORD_BOT_TOKEN)

def run_edit(text, callback):
    """
    🌟 重要修正：修正最後一則訊息的進入點
    解決 Timeout context manager 報錯：必須使用 run_coroutine_threadsafe 
    將任務丟回 Discord 正在運行的 Loop 中執行。
    """
    try:
        # 將 edit 任務安全地丟進 Discord 正在跑的小宇宙
        future = asyncio.run_coroutine_threadsafe(edit_last_logic(text), discord_client.loop)
        
        # 等待結果 (最長等待 10 秒)
        result = future.result(timeout=10) 
        
        if result is True:
            callback("📝 [系統] 訊息修正成功！")
        else:
            callback(f"⚠️ [警告] {result}")
    except Exception as e:
        callback(f"💥 [錯誤] 執行修正時發生異常: {e}")