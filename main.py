import os
import shutil
import threading

import customtkinter as ctk
import pystray
from PIL import Image

from logic import run_logic

class App(ctk.CTk):
    """ImageBOT 主控制介面"""
    
    def __init__(self):
        super().__init__()
        
        self.title("ImageBOT")
        self.geometry("700x650")
        try:
            self.iconbitmap("icon.ico")
        except Exception:
            pass

        self.running = False
        self.running_event = threading.Event()

        self._setup_ui()
        self.update_storage_label()
        self.create_tray()

    def _setup_ui(self):
        """初始化 UI 元件"""
        self.label_storage = ctk.CTkLabel(self, text="暫存佔用: 0.00 MB", font=("Microsoft JhengHei", 12))
        self.label_storage.pack(pady=10)

        self.log_view = ctk.CTkTextbox(self, width=660, height=250, font=("Consolas", 12))
        self.log_view.pack(pady=10, padx=20)

        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(fill="x", padx=20, pady=10)

        self.btn_start = ctk.CTkButton(self.btn_frame, text="啟動系統", command=self.launch)
        self.btn_start.pack(side="left", padx=5, expand=True)

        self.btn_clean = ctk.CTkButton(
            self.btn_frame, text="清理暫存", fg_color="#dc3545", 
            hover_color="#c82333", command=self.manual_clean
        )
        self.btn_clean.pack(side="left", padx=5, expand=True)

        self.btn_minimize = ctk.CTkButton(
            self.btn_frame, text="縮小到托盤", fg_color="#17a2b8", 
            hover_color="#138496", command=self.minimize_to_tray
        )
        self.btn_minimize.pack(side="left", padx=5, expand=True)

    def write_log(self, message: str):
        """將日誌寫入 UI 並滾動至最底"""
        self.log_view.insert("end", f"{message}\n")
        self.log_view.see("end")
        self.update_storage_label()

    def update_storage_label(self):
        """計算並更新本地媒體暫存資料夾大小"""
        total_size = 0
        for directory in ["images", "videos"]:
            if not os.path.exists(directory):
                continue
            for f in os.listdir(directory):
                fp = os.path.join(directory, f)
                if os.path.isfile(fp):
                    total_size += os.path.getsize(fp)
                    
        self.label_storage.configure(text=f"暫存佔用: {total_size/(1024*1024):.2f} MB")

    def launch(self):
        """啟動核心背景服務"""
        if self.running:
            self.write_log("[系統] 服務已在運行中")
            return

        self.running = True
        self.running_event.set()
        self.btn_start.configure(state="disabled", text="核心運行中...")
        self.write_log("[系統] 正在背景啟動系統核心...")
        
        threading.Thread(target=run_logic, args=(self.write_log, self.running_event), daemon=True).start()

    def manual_clean(self):
        """清空本地媒體暫存"""
        for folder in ["images", "videos"]:
            if os.path.exists(folder):
                shutil.rmtree(folder)
                os.makedirs(folder)
        self.write_log("[系統] 暫存資料夾已手動清空。")
        self.update_storage_label()

    def create_tray(self):
        """建立常駐系統匣 (System Tray)"""
        try:
            icon = Image.open("icon.ico")
        except Exception:
            icon = Image.new('RGB', (64, 64), color='blue')
        
        menu = pystray.Menu(
            pystray.MenuItem("顯示視窗", self.show_window),
            pystray.MenuItem("停止服務", self.stop_service),
            pystray.MenuItem("退出", self.quit_app)
        )
        
        self.tray = pystray.Icon("ImageBOT", icon, menu=menu)
        self.tray.run_detached()

    def show_window(self):
        self.deiconify()

    def stop_service(self):
        self.running = False
        self.running_event.clear()
        self.btn_start.configure(state="normal", text=" 啟動系統")
        self.write_log("[系統] 服務已停止")

    def quit_app(self):
        self.running = False
        self.tray.stop()
        self.quit()

    def minimize_to_tray(self):
        self.withdraw()

if __name__ == "__main__":
    app = App()
    app.mainloop()