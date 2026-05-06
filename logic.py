import os
import sys
import time
import json
import asyncio
import uuid
import tempfile
import shutil
import re
import urllib.parse
import hashlib

import discord
import boto3
from botocore.exceptions import ClientError
from boto3.s3.transfer import TransferConfig
from telethon import TelegramClient, events
from opencc import OpenCC
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# --- 讀取 JSON 設定檔 ---
def load_config():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

config_data = load_config()

# 建立動態映射表 (反轉字典以利快速查詢)
SERIES_MAPPING = {
    alias.lower(): real_name 
    for real_name, aliases in config_data["routing"]["series_mapping"].items() 
    for alias in aliases
}
ARTIST_MAPPING = {
    tag.lower(): channel 
    for channel, tags in config_data["routing"]["artist_mapping"].items() 
    for tag in tags
}
WORD_REPLACEMENTS = config_data["localization"]["replacements"]

# --- 基礎配置參數 ---
DISCORD_MAX_FILE_MB = int(os.getenv("DISCORD_MAX_FILE_MB", "0"))
RECOMMEND_COMPRESS_MB = int(os.getenv("RECOMMEND_COMPRESS_MB", "80"))
RECOMMEND_COMPRESS_DURATION_SEC = int(os.getenv("RECOMMEND_COMPRESS_DURATION_SEC", "300"))
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
FFPROBE_PATH = os.getenv("FFPROBE_PATH", "ffprobe")

# R2 相關設定
R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME")
R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL")

# Telegram & Discord 憑證
TG_API_ID = int(os.getenv('TG_API_ID', 0))
TG_API_HASH = os.getenv('TG_API_HASH')
TG_SOURCE_CHANNEL = os.getenv('TG_SOURCE_CHANNEL')
if TG_SOURCE_CHANNEL and TG_SOURCE_CHANNEL.lstrip('-').isdigit():
    TG_SOURCE_CHANNEL = int(TG_SOURCE_CHANNEL)

DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
DISCORD_SERVER_ID = int(os.getenv('DISCORD_SERVER_ID', 0))

# --- 全域狀態與客戶端 ---
cc = OpenCC('s2twp')
discord_client = discord.Client(intents=discord.Intents.default())
discord_client.intents.message_content = True

session_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bot_session')
tg_client = TelegramClient(session_path, TG_API_ID, TG_API_HASH)

album_cache = {}
album_tasks = {}
banned_albums = set()
logger = print  # 預設輸出，啟動時會被 UI callback 替換

last_captured_text = ""
last_text_time = 0

# --- 工具函式 ---

def localize(text: str) -> str:
    """文字繁體化與特定詞彙替換"""
    if not text:
        return ""
    converted = cc.convert(text)
    for src, tgt in WORD_REPLACEMENTS.items():
        converted = converted.replace(src, tgt)
    return converted

def is_advertisement(text: str) -> bool:
    """過濾無標籤之廣告訊息"""
    if not text:
        return False
    has_target = any(re.search(rf"{tag}.*?[:：]\s*(.*)", text, re.IGNORECASE) 
                     for tag in ["Character", "Artist", "Material"])
    return not has_target

def infer_server_limit(guild) -> int:
    """推斷 Discord 伺服器上傳限制 (Bytes)"""
    if DISCORD_MAX_FILE_MB > 0:
        return DISCORD_MAX_FILE_MB * 1024 * 1024
    tier = getattr(guild, "premium_tier", 0)
    mapping_mb = {0: 8, 1: 50, 2: 100, 3: 250}
    return mapping_mb.get(tier, 25) * 1024 * 1024

async def get_media_duration(path: str):
    """取得媒體時長"""
    try:
        proc = await asyncio.create_subprocess_exec(
            FFPROBE_PATH, "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        return float(stdout.decode().strip()) if stdout else None
    except Exception:
        return None

async def compress_with_ffmpeg_async(input_path: str, output_path: str, target_size_bytes: int) -> bool:
    """非同步壓縮影片，優先使用 AMD 硬體加速 (h264_amf)，失敗則退回 CPU 編碼"""
    duration = await get_media_duration(input_path)
    if not duration:
        return False

    target_total_bitrate = (target_size_bytes * 8) / duration
    target_video_bitrate = max(100, (target_total_bitrate / 1000) - 128)

    cmd_amd = [
        'ffmpeg', '-y', '-i', input_path,
        '-c:v', 'h264_amf', '-b:v', f'{int(target_video_bitrate)}k',
        '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', output_path
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd_amd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()

        if process.returncode == 0:
            return True

        logger(f"[系統] AMD 加速編碼失敗，切換至 CPU 模式。")
        
        cmd_cpu = [
            'ffmpeg', '-y', '-i', input_path,
            '-c:v', 'libx264', '-preset', 'ultrafast',
            '-b:v', f'{int(target_video_bitrate)}k',
            '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', output_path
        ]
        process_cpu = await asyncio.create_subprocess_exec(
            *cmd_cpu, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await process_cpu.communicate()
        return process_cpu.returncode == 0

    except Exception as e:
        logger(f"[錯誤] FFmpeg 執行異常: {e}")
        return False

async def upload_to_r2(path: str) -> str:
    """上傳大型檔案至 Cloudflare R2 並回傳直連 URL"""
    if not all([R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME, R2_PUBLIC_URL]):
        logger("[警告] 缺少 R2 設定，放棄上傳")
        return None

    original_ext = os.path.splitext(path)[1] or ".mp4"
    short_hash = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
    filename = f"v_{short_hash}{original_ext}"

    def _sync_upload():
        try:
            endpoint = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
            s3 = boto3.client(
                "s3", endpoint_url=endpoint, aws_access_key_id=R2_ACCESS_KEY_ID,
                aws_secret_access_key=R2_SECRET_ACCESS_KEY
            )
            config = TransferConfig(
                multipart_threshold=8 * 1024 * 1024, max_concurrency=10,
                multipart_chunksize=8 * 1024 * 1024, use_threads=True
            )
            s3.upload_file(path, R2_BUCKET_NAME, filename, Config=config)
            
            clean_url = R2_PUBLIC_URL.replace("https://", "").replace("http://", "").rstrip('/')
            return f"https://{clean_url}/{urllib.parse.quote(filename)}"
        except Exception as e:
            logger(f"[錯誤] R2 上傳失敗 {path}: {e}")
            return None

    return await asyncio.to_thread(_sync_upload)

# --- 核心處理與路由 ---

async def process_and_send(raw_text: str, file_paths: list):
    """解析標籤、分配頻道、處理檔案並發送至 Discord"""
    global last_captured_text, last_text_time

    guild = discord_client.get_guild(DISCORD_SERVER_ID)
    if not guild:
        logger("[錯誤] 找不到目標 Discord 伺服器。")
        return

    # 文字記憶機制
    current_time = time.time()
    if raw_text.strip():
        last_captured_text, last_text_time = raw_text, current_time
    elif (current_time - last_text_time) < 30:
        raw_text = last_captured_text

    # 標籤解析與路由判定
    all_hashtags = [tag.lower() for tag in re.findall(r'#([^\s#]+)', raw_text)]
    target_channel = None

    for tag in all_hashtags:
        dest = ARTIST_MAPPING.get(tag)
        if dest:
            target_channel = discord.utils.get(guild.text_channels, name=dest)
            break

    if not target_channel:
        for tag in all_hashtags:
            dest = SERIES_MAPPING.get(tag)
            if dest:
                target_channel = discord.utils.get(guild.text_channels, name=dest)
                break

    if not target_channel:
        target_channel = discord.utils.get(guild.text_channels, name=config_data["discord_target"]["default_channel"])

    if target_channel:
        logger(f"[分發] 鎖定目標頻道: #{target_channel.name}")

        # 格式化輸出文字
        extracted = {
            "char": re.search(r"Character.*?[:：]\s*(.*)", raw_text, re.IGNORECASE),
            "art": re.search(r"Artist.*?[:：]\s*(.*)", raw_text, re.IGNORECASE),
            "mat": re.search(r"Material.*?[:：]\s*(.*)", raw_text, re.IGNORECASE)
        }
        lines = [localize(m.group(1).strip()) for m in extracted.values() if m]
        custom_text = f"```\n{chr(10).join(lines)}\n```" if lines else ""

    server_limit = infer_server_limit(guild)
    safe_limit = max(8 * 1024 * 1024, server_limit - (2 * 1024 * 1024))
    recommend_bytes = RECOMMEND_COMPRESS_MB * 1024 * 1024

    ready_files, oversize_files, external_links, temp_to_delete = [], [], [], []

    # 檔案體積篩選
    for p in file_paths:
        if not os.path.exists(p): continue
        size = os.path.getsize(p)
        (ready_files if size <= safe_limit else oversize_files).append(p if size <= safe_limit else (p, size))

    # 大檔處理 (壓縮或上傳)
    for src_path, size in oversize_files:
        base_name = os.path.basename(src_path)
        duration = await get_media_duration(src_path) or 999999
        
        if size <= recommend_bytes and duration <= RECOMMEND_COMPRESS_DURATION_SEC:
            tmp_dst = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4().hex}.mp4")
            logger(f"[處理] 正在壓縮: {base_name}")
            ok = await compress_with_ffmpeg_async(src_path, tmp_dst, safe_limit)
            
            if ok and os.path.exists(tmp_dst) and os.path.getsize(tmp_dst) <= safe_limit:
                ready_files.append(tmp_dst)
                temp_to_delete.append(tmp_dst)
            else:
                logger(f"[處理] 壓縮未達標，轉交 R2 上傳: {base_name}")
                link = await upload_to_r2(src_path)
                if link: external_links.append(link)
        else:
            link = await upload_to_r2(src_path)
            if link: external_links.append(link)

    # 發送邏輯
    try:
        if ready_files:
            batches, current_batch, current_size = [], [], 0
            for fp in ready_files:
                size = os.path.getsize(fp)
                if (current_size + size > safe_limit) or (len(current_batch) >= 10):
                    batches.append(current_batch)
                    current_batch, current_size = [fp], size
                else:
                    current_batch.append(fp)
                    current_size += size
            if current_batch: batches.append(current_batch)

            for i, batch_paths in enumerate(batches):
                files = [discord.File(fp) for fp in batch_paths if os.path.exists(fp)]
                await target_channel.send(content=custom_text if i == 0 else "", files=files)
        elif custom_text and not external_links:
            await target_channel.send(content=custom_text)

        if external_links:
            await target_channel.send(content="\n".join(external_links))

        logger(f"[完成] 任務執行完畢。")

        # 清理
        await asyncio.sleep(1)
        for p in file_paths + temp_to_delete:
            if os.path.exists(p): os.remove(p)

    except Exception as e:
        logger(f"[錯誤] Discord 發送失敗: {e}")

# --- 服務啟動入口 ---

def run_logic(ui_callback, running_event):
    global logger
    logger = ui_callback
    os.makedirs("images", exist_ok=True)
    os.makedirs("videos", exist_ok=True)

    @tg_client.on(events.NewMessage(chats=TG_SOURCE_CHANNEL))
    async def handler(event):
        global banned_albums
        if not event.message.media: return

        gid = event.message.grouped_id
        text = event.message.text

        if gid and (gid in banned_albums): return
        if text and is_advertisement(text):
            logger("[攔截] 偵測到無效標籤或廣告。")
            if gid: banned_albums.add(gid)
            return

        if gid:
            if gid not in album_cache:
                album_cache[gid] = {"text": text or "", "messages": []}
            elif text:
                album_cache[gid]["text"] = text
            album_cache[gid]["messages"].append(event.message)

            if gid in album_tasks: album_tasks[gid].cancel()

            async def delayed_process(g_id):
                await asyncio.sleep(5)
                if g_id in album_cache:
                    data = album_cache.pop(g_id)
                    logger(f"[下載] 開始擷取相簿媒體 (共 {len(data['messages'])} 件)...")
                    
                    file_paths = []
                    for msg in data["messages"]:
                        folder = "images/" if msg.photo else "videos/"
                        p = await msg.download_media(file=folder)
                        if p: file_paths.append(p)
                    await process_and_send(data["text"], file_paths)

            album_tasks[gid] = asyncio.create_task(delayed_process(gid))
        else:
            folder = "images/" if event.message.photo else "videos/"
            path = await event.message.download_media(file=folder)
            if path: await process_and_send(text or "", [path])

    @discord_client.event
    async def on_ready():
        logger(f"[系統] Discord 機器人連線成功: {discord_client.user}")
        try:
            await tg_client.start()
            await tg_client.get_entity(TG_SOURCE_CHANNEL)
            logger("[系統] Telegram 監聽服務啟動。")
        except Exception as e:
            logger(f"[錯誤] Telegram 啟動失敗: {e}")

    discord_client.run(DISCORD_BOT_TOKEN)