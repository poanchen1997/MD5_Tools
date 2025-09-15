import hashlib
import json
import os
import queue
import threading
import time
import sys
from datetime import datetime
from tkinter import Tk, Button, Text, END, DISABLED, NORMAL, filedialog, ttk, messagebox, PhotoImage, Label, Frame
from PIL import Image, ImageTk

APP_NAME = "MD5 Folder Tool by InstantNano"
MANIFEST_NAME = "_md5_manifest.json"
CHUNK_SIZE = 1024 * 1024  # 1 MB

def win_longpath(p: str) -> str:
    # 在 Windows 加上長路徑前綴（避免 260 字元限制）
    if os.name == "nt":
        p = os.path.abspath(p)
        if not p.startswith("\\\\?\\"):
            if p.startswith("\\\\"):
                # 網路路徑 \\server\share -> \\?\UNC\server\share
                p = "\\\\?\\UNC" + p[1:]
            else:
                p = "\\\\?\\" + p
    return p

def resource_path(rel_path: str) -> str:
    # PyInstaller 打包後，臨時資源目錄在 sys._MEIPASS
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, rel_path)

def iter_files(root_dir: str):
    for base, dirs, files in os.walk(root_dir):
        for name in files:
            yield os.path.join(base, name)

def md5_of_file(path: str) -> str:
    h = hashlib.md5()
    with open(win_longpath(path), "rb", buffering=0) as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def rel_path(path: str, root_dir: str) -> str:
    return os.path.relpath(path, start=root_dir).replace("\\", "/")

def load_manifest(manifest_path: str):
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_manifest(manifest_path: str, data: dict):
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

class Md5ToolGUI:
    def __init__(self, master: Tk):
        self.master = master
        master.title(APP_NAME)
        master.geometry("820x520")

        # === 上方：Logo（左） + Spacer（中） + 按鈕群（右） ===
        top_frame = Frame(master)
        top_frame.pack(fill="x", pady=10, padx=10)

        # 讓第 1 欄（中間 spacer）吃掉多餘寬度
        top_frame.grid_columnconfigure(0, weight=0)
        top_frame.grid_columnconfigure(1, weight=1)  # 中間自動撐開
        top_frame.grid_columnconfigure(2, weight=0)

        # 左邊 Logo
        try:
            img = Image.open(resource_path("Assets/Instant Logo.png"))
            img = img.resize((240, 60))  # 依需求調整
            self.logo_img = ImageTk.PhotoImage(img)
            logo_label = Label(top_frame, image=self.logo_img)
            logo_label.grid(row=0, column=0, padx=(0, 10), pady=0, sticky="w")
        except Exception as e:
            print(f"載入 Logo 失敗: {e}")

        # 中間 spacer（可用空 Label 或 Frame 皆可）
        spacer = Frame(top_frame)
        spacer.grid(row=0, column=1, sticky="nsew")

        # 右邊按鈕群
        btn_frame = Frame(top_frame)
        btn_frame.grid(row=0, column=2, padx=(10, 0), sticky="e")

        self.btn_make = Button(btn_frame, text="① 產生 MD5 清單檔", width=24, command=self.on_make_manifest)
        self.btn_make.pack(pady=5)

        self.btn_verify = Button(btn_frame, text="② 比對資料夾與 MD5 清單", width=24, command=self.on_verify_manifest)
        self.btn_verify.pack(pady=5)

        self.progress = ttk.Progressbar(master, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", padx=12, pady=8)

        self.log = Text(master, height=24)
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.log_queue = queue.Queue()
        self._poll_log()

        self.working = False
        self.lock_ui(False)

    # ---------- UI helpers ----------
    def lock_ui(self, busy: bool):
        self.working = busy
        state = DISABLED if busy else NORMAL
        self.btn_make.config(state=state)
        self.btn_verify.config(state=state)

    def log_write(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_queue.put(f"[{ts}] {msg}\n")

    def _poll_log(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.log.insert(END, line)
                self.log.see(END)
        except queue.Empty:
            pass
        self.master.after(80, self._poll_log)

    def set_progress(self, value: int, maximum: int):
        self.progress["maximum"] = max(1, maximum)
        self.progress["value"] = value
        self.master.update_idletasks()

    # ---------- Actions ----------
    def on_make_manifest(self):
        folder = filedialog.askdirectory(title="選擇要建立 MD5 清單的資料夾")
        if not folder:
            return

        manifest_path = os.path.join(folder, MANIFEST_NAME)

        # 若清單已存在：提示是否覆蓋，並先嘗試自動備份
        if os.path.exists(manifest_path):
            overwrite = messagebox.askyesno(
                APP_NAME,
                "偵測到此資料夾已存在 MD5 清單檔（_md5_manifest.json）。\n\n"
                "是否要重新產生並覆蓋？"
            )
            if not overwrite:
                self.log_write("使用者取消：保留既有 _md5_manifest.json")
                return

            # 覆蓋前自動備份 -> 先移除,感覺會讓使用者誤會
            # try:
            #     import shutil
            #     bak_path = manifest_path + ".bak"
            #     shutil.copy2(manifest_path, bak_path)
            #     self.log_write("已建立清單備份：_md5_manifest.json.bak")
            # except Exception as e:
            #     # 備份失敗時再確認一次是否仍要覆蓋
            #     proceed = messagebox.askyesno(
            #         APP_NAME,
            #         f"清單備份失敗：{e}\n\n是否仍要覆蓋舊清單？"
            #     )
            #     if not proceed:
            #         self.log_write("使用者取消：因備份失敗，不覆蓋清單")
            #         return

        threading.Thread(
            target=self._make_manifest_worker,
            args=(folder,),
            daemon=True
        ).start()

    def _make_manifest_worker(self, folder: str):
        if self.working:
            return
        self.lock_ui(True)
        self.log_write(f"開始建立清單：{folder}")

        try:
            all_files = list(iter_files(folder))
            # 排除清單檔與常見 checksum 檔、與備份檔
            exclude_names = {MANIFEST_NAME, "MD5SUMS.txt", "checksums.md5", MANIFEST_NAME + ".bak"}
            files = [p for p in all_files if os.path.basename(p) not in exclude_names]

            total = len(files)
            self.set_progress(0, total)
            entries = []

            for i, fpath in enumerate(files, 1):
                try:
                    rp = rel_path(fpath, folder)
                    size = os.path.getsize(fpath)
                    mtime = int(os.path.getmtime(fpath))
                    digest = md5_of_file(fpath)
                    entries.append({
                        "path": rp,
                        "md5": digest,
                        "size": size,
                        "mtime": mtime
                    })
                    self.log_write(f"OK  {rp}  {digest}")
                except Exception as e:
                    self.log_write(f"ERR {fpath}: {e}")
                finally:
                    self.set_progress(i, total)

            manifest = {
                "tool": APP_NAME,
                "algorithm": "md5",
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "root_hint": os.path.basename(os.path.abspath(folder)),
                "entries": entries
            }

            manifest_path = os.path.join(folder, MANIFEST_NAME)
            save_manifest(manifest_path, manifest)
            self.log_write(f"完成。清單已寫入：{manifest_path}")
            messagebox.showinfo(APP_NAME, f"清單建立完成：\n{manifest_path}")

        finally:
            self.lock_ui(False)
            self.set_progress(0, 1)



    def on_verify_manifest(self):
        folder = filedialog.askdirectory(title="選擇要比對的根資料夾（含清單）")
        if not folder:
            return
        threading.Thread(target=self._verify_manifest_worker, args=(folder,), daemon=True).start()

    # ---------- Workers ----------
    def _verify_manifest_worker(self, folder: str):
        if self.working:
            return
        self.lock_ui(True)
        try:
            manifest_path = os.path.join(folder, MANIFEST_NAME)
            if not os.path.exists(manifest_path):
                # 兼容提示：若看到傳統 MD5SUMS.txt，仍請使用本工具產生 JSON 清單
                alt = os.path.join(folder, "MD5SUMS.txt")
                if os.path.exists(alt):
                    messagebox.showwarning(
                        APP_NAME,
                        "偵測到 MD5SUMS.txt，但本工具預設使用 JSON 清單（_md5_manifest.json）。\n"
                        "請先用「① 產生 MD5 清單檔」建立 JSON 清單後再比對。"
                    )
                    self.lock_ui(False)
                    return

                # 明確引導：回到來源機器用按鈕① 產生清單，並將清單檔放回此資料夾
                messagebox.showerror(
                    APP_NAME,
                    "找不到清單檔：_md5_manifest.json\n\n"
                    "請先在『原本的機器』上於來源資料夾執行按鈕①「產生 MD5 清單檔」，\n"
                    "完成後將 _md5_manifest.json 與檔案一起搬移到目前的資料夾，再執行比對。"
                )
                self.lock_ui(False)
                return

            self.log_write(f"載入清單：{manifest_path}")
            manifest = load_manifest(manifest_path)
            expected = {e["path"]: e for e in manifest.get("entries", [])}

            # 掃描目前資料夾的檔案（排除清單檔與常見校驗檔）
            exclude_names = {MANIFEST_NAME, "MD5SUMS.txt", "checksums.md5"}
            actual_files = [p for p in iter_files(folder) if os.path.basename(p) not in exclude_names]
            actual_rel = {rel_path(p, folder): p for p in actual_files}

            missing = []     # 清單有、資料夾沒有
            extras = []      # 清單沒有、資料夾多出
            size_mismatch = []
            hash_mismatch = []

            # 先針對清單逐一檢查
            self.set_progress(0, len(expected))
            for i, (rp, meta) in enumerate(expected.items(), 1):
                fpath = actual_rel.get(rp)
                if not fpath:
                    missing.append(rp)
                else:
                    try:
                        size = os.path.getsize(fpath)
                        if size != int(meta.get("size", -1)):
                            size_mismatch.append(rp)
                        # 計算 MD5
                        digest = md5_of_file(fpath)
                        if digest.lower() != meta.get("md5", "").lower():
                            hash_mismatch.append(rp)
                            self.log_write(f"MD5 不符：{rp}  清單:{meta.get('md5')}  現況:{digest}")
                        else:
                            self.log_write(f"OK  {rp}")
                    except Exception as e:
                        self.log_write(f"ERR {rp}: {e}")
                self.set_progress(i, len(expected))

            # 找出多出的檔案
            for rp in actual_rel.keys():
                if rp not in expected:
                    extras.append(rp)

            # 彙整結果
            self.log_write("—— 比對摘要 ——")
            self.log_write(f"清單總數：{len(expected)}")
            self.log_write(f"OK 數量：{len(expected) - (len(missing)+len(size_mismatch)+len(hash_mismatch))}")
            self.log_write(f"遺失檔案：{len(missing)}")
            self.log_write(f"大小不符：{len(size_mismatch)}")
            self.log_write(f"雜湊不符：{len(hash_mismatch)}")
            self.log_write(f"多出檔案：{len(extras)}")

            details = []
            if missing:
                details.append(f"遺失 {len(missing)} 筆（僅列前 10）:\n  - " + "\n  - ".join(missing[:10]))
            if size_mismatch:
                details.append(f"大小不符 {len(size_mismatch)} 筆（前 10）:\n  - " + "\n  - ".join(size_mismatch[:10]))
            if hash_mismatch:
                details.append(f"MD5 不符 {len(hash_mismatch)} 筆（前 10）:\n  - " + "\n  - ".join(hash_mismatch[:10]))
            if extras:
                details.append(f"多出 {len(extras)} 筆（前 10）:\n  - " + "\n  - ".join(extras[:10]))

            if missing or size_mismatch or hash_mismatch:
                messagebox.showerror(APP_NAME, "比對發現異常：\n\n" + ("\n\n".join(details) if details else ""))
            elif extras:
                messagebox.showwarning(APP_NAME, "檔案內容皆通過，但資料夾有額外檔案：\n\n" + ("\n\n".join(details) if details else ""))
            else:
                messagebox.showinfo(APP_NAME, "比對完成，全部通過。")

        finally:
            self.lock_ui(False)
            self.set_progress(0, 1)


def main():
    root = Tk()
    try:
        # Windows 上建議 .ico；這是「視窗左上角」的小圖示
        root.iconbitmap(resource_path("Assets/Instant Icon.ico"))
    except Exception as e:
        print("iconbitmap 設定失敗：", e)
    # 改用 ttk 風格
    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass
    app = Md5ToolGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
