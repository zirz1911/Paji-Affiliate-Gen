import queue
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import List

import customtkinter as ctk
from tkinter import messagebox

from api.gemini_tts import GeminiTTSClient
from ui.settings_dialog import SettingsDialog
from ui.task_form import AddTaskDialog
from utils.config import Config, AffiliateTask
from utils.file import safe_filename, get_video_files
from video.editor import build_video

# Status display
STATUS_ICONS = {
    "pending": "⏳",
    "processing": "⚙️",
    "done": "✅",
    "error": "❌",
}

COL_HEADERS = ["#", "Task Name", "Folder", "Scripts", "Voice", "Status"]
COL_WIDTHS   = [30,   180,        220,      60,        80,      80]


class MainApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("🎬 Paji Affiliate Gen")
        self.geometry("820x580")
        self.minsize(700, 480)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.config = Config.load()
        self.tasks: List[AffiliateTask] = []
        self._ui_queue: queue.Queue = queue.Queue()
        self._executor: ThreadPoolExecutor = None

        self._check_ffmpeg()
        self._build()
        self._poll_ui_queue()

    # ── UI Build ──────────────────────────────────────────────────────────────

    def _build(self):
        # Header
        header = ctk.CTkFrame(self, height=50, fg_color=("gray85", "gray20"))
        header.pack(fill="x")
        ctk.CTkLabel(header, text="🎬 Paji Affiliate Gen",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(side="left", padx=16)
        ctk.CTkButton(header, text="Settings", width=90,
                      command=self._open_settings).pack(side="right", padx=12, pady=8)

        # Toolbar
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=8, pady=4)
        ctk.CTkButton(toolbar, text="+ Add Task", width=100, command=self._add_task).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="✏ Edit", width=80, command=self._edit_task).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="🗑 Delete", width=80, fg_color="gray40",
                      command=self._delete_task).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="▶ Generate All", width=120,
                      command=self._generate_all).pack(side="right", padx=4)

        # Table
        table_frame = ctk.CTkFrame(self)
        table_frame.pack(fill="both", expand=True, padx=8, pady=4)

        # Header row
        hrow = ctk.CTkFrame(table_frame, fg_color=("gray70", "gray30"), height=28)
        hrow.pack(fill="x")
        hrow.pack_propagate(False)
        for header_text, w in zip(COL_HEADERS, COL_WIDTHS):
            ctk.CTkLabel(hrow, text=header_text, width=w,
                         font=ctk.CTkFont(weight="bold"),
                         anchor="w").pack(side="left", padx=4)

        # Scrollable body
        self._table_body = ctk.CTkScrollableFrame(table_frame)
        self._table_body.pack(fill="both", expand=True)
        self._row_frames = []

        # Log area
        log_frame = ctk.CTkFrame(self, height=130)
        log_frame.pack(fill="x", padx=8, pady=(0, 8))
        log_frame.pack_propagate(False)
        ctk.CTkLabel(log_frame, text="Activity Log",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=8, pady=(4, 0))
        self._log_box = ctk.CTkTextbox(log_frame, state="disabled", font=ctk.CTkFont(size=11))
        self._log_box.pack(fill="both", expand=True, padx=8, pady=(0, 6))

    # ── Table rendering ───────────────────────────────────────────────────────

    def _refresh_table(self):
        for rf in self._row_frames:
            rf.destroy()
        self._row_frames.clear()

        for i, task in enumerate(self.tasks):
            bg = ("gray80", "gray25") if i % 2 == 0 else ("gray75", "gray22")
            row = ctk.CTkFrame(self._table_body, fg_color=bg, height=28)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            values = [
                str(i + 1),
                task.name,
                task.folder,
                str(len(task.scripts)),
                task.voice,
                STATUS_ICONS.get(task.status, task.status),
            ]
            for val, w in zip(values, COL_WIDTHS):
                ctk.CTkLabel(row, text=val, width=w, anchor="w").pack(side="left", padx=4)

            row.bind("<Button-1>", lambda e, idx=i: self._select_row(idx))
            self._row_frames.append(row)

        self._selected = None

    def _select_row(self, idx: int):
        self._selected = idx
        for i, rf in enumerate(self._row_frames):
            rf.configure(fg_color=("dodgerblue", "steelblue") if i == idx
                         else (("gray80", "gray25") if i % 2 == 0 else ("gray75", "gray22")))

    # ── Actions ───────────────────────────────────────────────────────────────

    def _open_settings(self):
        dlg = SettingsDialog(self, self.config)
        self.wait_window(dlg)

    def _add_task(self):
        dlg = AddTaskDialog(self, self.config)
        self.wait_window(dlg)
        if dlg.result:
            self.tasks.append(dlg.result)
            self._refresh_table()

    def _edit_task(self):
        idx = getattr(self, "_selected", None)
        if idx is None or idx >= len(self.tasks):
            return
        dlg = AddTaskDialog(self, self.config, task=self.tasks[idx])
        self.wait_window(dlg)
        if dlg.result:
            self._refresh_table()

    def _delete_task(self):
        idx = getattr(self, "_selected", None)
        if idx is None or idx >= len(self.tasks):
            return
        name = self.tasks[idx].name
        if messagebox.askyesno("Delete Task", f"Delete task '{name}'?"):
            self.tasks.pop(idx)
            self._selected = None
            self._refresh_table()

    def _generate_all(self):
        if not self.config.api_key:
            messagebox.showwarning("No API Key", "Please set your Google AI Studio API key in Settings.")
            return
        pending = [t for t in self.tasks if t.status in ("pending", "error")]
        if not pending:
            messagebox.showinfo("Nothing to do", "No pending tasks.")
            return
        self._executor = ThreadPoolExecutor(max_workers=self.config.max_concurrent)
        for task in pending:
            task.status = "processing"
        self._refresh_table()
        for task in pending:
            self._executor.submit(self._process_task, task)

    # ── Processing ────────────────────────────────────────────────────────────

    def _process_task(self, task: AffiliateTask):
        def log(msg: str):
            self._ui_queue.put(("log", f'[{datetime.now().strftime("%H:%M:%S")}] [{task.name}] {msg}'))

        try:
            client = GeminiTTSClient(self.config.api_key, self.config.model)
            video_files = get_video_files(task.folder)
            if not video_files:
                raise RuntimeError(f"No video files in: {task.folder}")

            for n, script in enumerate(task.scripts, start=1):
                safe = safe_filename(task.name)
                mp3_path = f"{task.folder}/{safe}_script_{n}.mp3"
                mp4_path = f"{task.folder}/{safe}_script_{n}.mp4"

                log(f"Script {n}/{len(task.scripts)} → TTS...")
                client.synthesize(script, task.voice, mp3_path)
                log(f"Script {n} TTS done → {mp3_path}")

                log(f"Script {n} → Building video...")
                build_video(mp3_path, video_files, mp4_path, task.clip_duration, log=log)
                log(f"Script {n} done → {mp4_path}")

            task.status = "done"
            log("All scripts complete ✅")

        except Exception as e:
            task.status = "error"
            log(f"ERROR: {e}")

        self._ui_queue.put(("refresh", None))

    # ── UI Polling ────────────────────────────────────────────────────────────

    def _poll_ui_queue(self):
        try:
            while True:
                msg_type, data = self._ui_queue.get_nowait()
                if msg_type == "log":
                    self._append_log(data)
                elif msg_type == "refresh":
                    self._refresh_table()
        except queue.Empty:
            pass
        self.after(100, self._poll_ui_queue)

    def _append_log(self, text: str):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", text + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    # ── Startup ───────────────────────────────────────────────────────────────

    def _check_ffmpeg(self):
        try:
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True)
            if result.returncode != 0:
                raise FileNotFoundError
        except FileNotFoundError:
            messagebox.showwarning(
                "ffmpeg not found",
                "ffmpeg is not installed or not in PATH.\n"
                "Please install ffmpeg and add it to PATH, then restart.\n\n"
                "Download: https://ffmpeg.org/download.html"
            )
