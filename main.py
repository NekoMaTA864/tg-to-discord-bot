# main.py
import customtkinter as ctk
import threading, os, shutil
from logic import run_logic, run_edit 

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # 1. 視窗設定
        self.title("ImageBOT Pro - 轉傳管理系統")
        self.geometry("700x650")
        try: self.iconbitmap("icon.ico")
        except: pass

        # 2. 空間佔用顯示
        self.label_storage = ctk.CTkLabel(self, text="💾 暫存佔用: 0.00 MB", font=("Microsoft JhengHei", 12))
        self.label_storage.pack(pady=10)

        # 3. 日誌視窗 (顯示運行狀態)
        self.log_view = ctk.CTkTextbox(self, width=660, height=250, font=("Consolas", 12))
        self.log_view.pack(pady=10, padx=20)

        # 4. ✏️ 修正區 (編輯框)
        self.label_edit = ctk.CTkLabel(self, text="📝 修正區 (在此輸入正確文字後按修正按鈕):", font=("Microsoft JhengHei", 12, "bold"))
        self.label_edit.pack(pady=(10, 0))
        # 藍色邊框的編輯框
        self.edit_box = ctk.CTkTextbox(self, width=660, height=120, border_width=2, border_color="#1f538d")
        self.edit_box.pack(pady=5, padx=20)

        # 5. 按鈕區
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(fill="x", padx=20, pady=10)

        self.btn_start = ctk.CTkButton(self.btn_frame, text="🚀 啟動系統", command=self.launch)
        self.btn_start.pack(side="left", padx=5, expand=True)

        self.btn_fix = ctk.CTkButton(self.btn_frame, text="✏️ 修正最後一則", fg_color="#1f538d", hover_color="#14375e", command=self.handle_fix)
        self.btn_fix.pack(side="left", padx=5, expand=True)

        self.btn_clean = ctk.CTkButton(self.btn_frame, text="🧹 清理暫存", fg_color="#dc3545", hover_color="#c82333", command=self.manual_clean)
        self.btn_clean.pack(side="left", padx=5, expand=True)

        self.update_storage_label()

    def write_log(self, message):
        """同步更新 Log 與空間顯示"""
        self.log_view.insert("end", f"{message}\n")
        self.log_view.see("end")
        self.update_storage_label()

    def update_storage_label(self):
        """掃描 images 和 videos 資料夾的大小"""
        size = 0
        for d in ["images", "videos"]:
            if os.path.exists(d):
                for f in os.listdir(d):
                    fp = os.path.join(d, f)
                    if os.path.isfile(fp): size += os.path.getsize(fp)
        self.label_storage.configure(text=f"💾 暫存佔用: {size/(1024*1024):.2f} MB")

    def launch(self):
        """按下啟動按鈕的動作"""
        self.btn_start.configure(state="disabled", text="核心運行中...")
        self.write_log("🚀 正在背景啟動系統核心...")
        # 啟動 Thread 跑機器人，介面才不會卡死
        threading.Thread(target=run_logic, args=(self.write_log,), daemon=True).start()

    def handle_fix(self):
        """點擊『修正最後一則』的動作"""
        # 抓取藍色編輯框內容
        new_text = self.edit_box.get("1.0", "end-1c").strip()
        if new_text:
            self.write_log("🔄 正在嘗試修正 Discord 上的最後一則訊息...")
            # 啟動 Thread 執行修正動作
            threading.Thread(target=run_edit, args=(new_text, self.write_log), daemon=True).start()
        else:
            self.write_log("⚠️ 請先在藍色編輯框輸入要修正的文字。")

    def manual_clean(self):
        """手動清理按鈕"""
        for f in ["images", "videos"]:
            if os.path.exists(f): shutil.rmtree(f); os.makedirs(f)
        self.write_log("✨ [系統] 暫存資料夾已手動清空。")
        self.update_storage_label()

if __name__ == "__main__":
    app = App()
    app.mainloop()