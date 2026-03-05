import customtkinter as ctk
from utils.config import Config
from api.gemini_tts import VOICES

MODELS = [
    "gemini-2.5-flash-tts",
    "gemini-2.5-pro-tts",
    "gemini-2.5-flash-lite-preview-tts",
]


class SettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, config: Config):
        super().__init__(parent)
        self.config = config
        self.title("Settings")
        self.geometry("460x340")
        self.resizable(False, False)
        self.grab_set()
        self._show_key = False
        self._build()

    def _build(self):
        pad = {"padx": 16, "pady": 6}

        ctk.CTkLabel(self, text="Google AI Studio API Key").pack(anchor="w", **pad)
        key_row = ctk.CTkFrame(self, fg_color="transparent")
        key_row.pack(fill="x", padx=16, pady=0)
        self._key_var = ctk.StringVar(value=self.config.api_key)
        self._key_entry = ctk.CTkEntry(key_row, textvariable=self._key_var, show="*", width=340)
        self._key_entry.pack(side="left", fill="x", expand=True)
        self._eye_btn = ctk.CTkButton(key_row, text="👁", width=36, command=self._toggle_key)
        self._eye_btn.pack(side="left", padx=(6, 0))

        ctk.CTkLabel(self, text="Model").pack(anchor="w", **pad)
        self._model_var = ctk.StringVar(value=self.config.model)
        ctk.CTkOptionMenu(self, variable=self._model_var, values=MODELS, width=340).pack(anchor="w", **pad)

        ctk.CTkLabel(self, text="Default Voice").pack(anchor="w", **pad)
        self._voice_var = ctk.StringVar(value=self.config.default_voice)
        ctk.CTkOptionMenu(self, variable=self._voice_var, values=VOICES, width=340).pack(anchor="w", **pad)

        ctk.CTkLabel(self, text="Default Clip Duration (seconds)").pack(anchor="w", **pad)
        self._dur_var = ctk.StringVar(value=str(self.config.default_clip_duration))
        ctk.CTkEntry(self, textvariable=self._dur_var, width=120).pack(anchor="w", **pad)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=16)
        ctk.CTkButton(btn_row, text="Save", command=self._save).pack(side="right")
        ctk.CTkButton(btn_row, text="Cancel", fg_color="gray40",
                      command=self.destroy).pack(side="right", padx=(0, 8))

    def _toggle_key(self):
        self._show_key = not self._show_key
        self._key_entry.configure(show="" if self._show_key else "*")

    def _save(self):
        try:
            dur = float(self._dur_var.get())
        except ValueError:
            dur = self.config.default_clip_duration

        self.config.api_key = self._key_var.get().strip()
        self.config.model = self._model_var.get()
        self.config.default_voice = self._voice_var.get()
        self.config.default_clip_duration = dur
        self.config.save()
        self.destroy()
