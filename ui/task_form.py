import tkinter as tk
from tkinter import filedialog
import customtkinter as ctk
from utils.config import Config, AffiliateTask
from api.gemini_tts import VOICES


class AddTaskDialog(ctk.CTkToplevel):
    def __init__(self, parent, config: Config, task: AffiliateTask = None):
        super().__init__(parent)
        self.config = config
        self.result: AffiliateTask = None
        self._editing = task
        self.title("Edit Task" if task else "Add Task")
        self.geometry("560x620")
        self.resizable(False, True)
        self.grab_set()
        self._script_rows = []
        self._build()
        if task:
            self._load(task)

    def _build(self):
        pad = {"padx": 16, "pady": 5}

        ctk.CTkLabel(self, text="Task Name").pack(anchor="w", **pad)
        self._name_var = ctk.StringVar()
        ctk.CTkEntry(self, textvariable=self._name_var, width=500).pack(anchor="w", **pad)

        ctk.CTkLabel(self, text="Video Footage Folder").pack(anchor="w", **pad)
        folder_row = ctk.CTkFrame(self, fg_color="transparent")
        folder_row.pack(fill="x", padx=16, pady=0)
        self._folder_var = ctk.StringVar()
        ctk.CTkEntry(folder_row, textvariable=self._folder_var, width=420).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(folder_row, text="Browse", width=70, command=self._browse).pack(side="left", padx=(6, 0))

        options_row = ctk.CTkFrame(self, fg_color="transparent")
        options_row.pack(fill="x", padx=16, pady=8)

        voice_col = ctk.CTkFrame(options_row, fg_color="transparent")
        voice_col.pack(side="left", padx=(0, 24))
        ctk.CTkLabel(voice_col, text="Voice").pack(anchor="w")
        self._voice_var = ctk.StringVar(value=self.config.default_voice)
        ctk.CTkOptionMenu(voice_col, variable=self._voice_var, values=VOICES, width=160).pack()

        dur_col = ctk.CTkFrame(options_row, fg_color="transparent")
        dur_col.pack(side="left")
        ctk.CTkLabel(dur_col, text="Clip Duration (sec)").pack(anchor="w")
        self._dur_var = ctk.StringVar(value=str(self.config.default_clip_duration))
        ctk.CTkEntry(dur_col, textvariable=self._dur_var, width=100).pack()

        # Scripts section
        scripts_header = ctk.CTkFrame(self, fg_color="transparent")
        scripts_header.pack(fill="x", padx=16, pady=(8, 0))
        ctk.CTkLabel(scripts_header, text="Scripts", font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkButton(scripts_header, text="+ Add Script", width=100,
                      command=self._add_script_row).pack(side="right")

        # Scrollable scripts area
        self._scripts_frame = ctk.CTkScrollableFrame(self, height=260)
        self._scripts_frame.pack(fill="both", expand=True, padx=16, pady=6)

        # Buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=10)
        ctk.CTkButton(btn_row, text="Save", command=self._save).pack(side="right")
        ctk.CTkButton(btn_row, text="Cancel", fg_color="gray40",
                      command=self.destroy).pack(side="right", padx=(0, 8))

        # Start with one empty script
        self._add_script_row()

    def _browse(self):
        path = filedialog.askdirectory(title="Select Video Footage Folder")
        if path:
            self._folder_var.set(path)

    def _add_script_row(self, text: str = ""):
        row = ctk.CTkFrame(self._scripts_frame, fg_color="transparent")
        row.pack(fill="x", pady=4)

        txt = ctk.CTkTextbox(row, height=80, wrap="word")
        txt.pack(side="left", fill="x", expand=True)
        if text:
            txt.insert("1.0", text)

        def remove(r=row, t=txt):
            self._script_rows = [(rr, tt) for rr, tt in self._script_rows if tt is not t]
            r.destroy()

        ctk.CTkButton(row, text="✕", width=32, fg_color="gray40",
                      command=remove).pack(side="left", padx=(4, 0))
        self._script_rows.append((row, txt))

    def _load(self, task: AffiliateTask):
        self._name_var.set(task.name)
        self._folder_var.set(task.folder)
        self._voice_var.set(task.voice)
        self._dur_var.set(str(task.clip_duration))
        # Clear default row, then load scripts
        for row, _ in self._script_rows:
            row.destroy()
        self._script_rows.clear()
        for s in task.scripts:
            self._add_script_row(s)

    def _save(self):
        name = self._name_var.get().strip()
        folder = self._folder_var.get().strip()
        if not name or not folder:
            return

        scripts = []
        for _, txt in self._script_rows:
            content = txt.get("1.0", "end").strip()
            if content:
                scripts.append(content)

        if not scripts:
            return

        try:
            dur = float(self._dur_var.get())
        except ValueError:
            dur = self.config.default_clip_duration

        if self._editing:
            self._editing.name = name
            self._editing.folder = folder
            self._editing.scripts = scripts
            self._editing.voice = self._voice_var.get()
            self._editing.clip_duration = dur
            self.result = self._editing
        else:
            self.result = AffiliateTask(
                name=name,
                folder=folder,
                scripts=scripts,
                voice=self._voice_var.get(),
                clip_duration=dur,
            )
        self.destroy()
