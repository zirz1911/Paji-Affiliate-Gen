import json
import os
import tkinter as tk
from dataclasses import asdict
from pathlib import Path
from tkinter import filedialog, colorchooser, simpledialog, messagebox
from typing import List, Any, Optional

import customtkinter as ctk
from PIL import Image, ImageTk

from utils.config import AffiliateTask, TextOverlay, ImageOverlay
from utils.fonts import font_names, font_path_for

PRESET_DIR = Path.home() / ".paji-affiliate" / "presets"

RATIO_SPECS = {
    "9:16": {"cw": 360, "ch": 640, "rw": 1080, "rh": 1920, "win": "780x720"},
    "16:9": {"cw": 640, "ch": 360, "rw": 1920, "rh": 1080, "win": "1020x460"},
}

_FONTS: Optional[List[str]] = None


def _get_fonts() -> List[str]:
    global _FONTS
    if _FONTS is None:
        _FONTS = font_names() or ["Tahoma", "Arial", "Calibri"]
    return _FONTS


def _overlay_from_dict(d: dict) -> Any:
    if d.get("type") == "text":
        return TextOverlay(**{k: v for k, v in d.items() if k in TextOverlay.__dataclass_fields__})
    return ImageOverlay(**{k: v for k, v in d.items() if k in ImageOverlay.__dataclass_fields__})


class OverlayEditor(ctk.CTkToplevel):
    def __init__(self, parent, task: AffiliateTask):
        super().__init__(parent)
        self.task = task
        self.title(f"Overlay Editor — {task.name}")
        self.resizable(True, True)
        self.grab_set()

        self._overlays: List[Any] = list(task.overlays)
        self._selected: Optional[str] = None
        self._drag_start = None
        self._shift_axis: Optional[str] = None
        self._img_cache = {}
        self._ratio: str = task.overlay_ratio
        self._cw = self._ch = self._rw = self._rh = 0

        self._build()
        self._apply_ratio(self._ratio, init=True)
        self._refresh_list()
        self._redraw()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.pack(side="left", padx=(12, 8), pady=12, fill="y")

        # Ratio selector
        ratio_row = ctk.CTkFrame(left, fg_color="transparent")
        ratio_row.pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(ratio_row, text="Ratio:", font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 6))
        self._ratio_btns = {}
        for r in ("9:16", "16:9"):
            btn = ctk.CTkButton(ratio_row, text=r, width=64, height=26,
                                command=lambda ratio=r: self._apply_ratio(ratio))
            btn.pack(side="left", padx=2)
            self._ratio_btns[r] = btn

        self._hint_label = ctk.CTkLabel(left, text="", font=ctk.CTkFont(size=10), text_color="gray55")
        self._hint_label.pack(anchor="w")

        self._border = tk.Frame(left, bd=2, relief="sunken", bg="#0d0d0d")
        self._border.pack()
        self._canvas = tk.Canvas(self._border, bg="#111111",
                                 highlightthickness=0, cursor="crosshair")
        self._canvas.pack()
        self._canvas.bind("<ButtonPress-1>",  self._on_press)
        self._canvas.bind("<B1-Motion>",       self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)

        # Keyboard shortcuts — bound at window level so they work
        # regardless of Thai/English IME (special keys are IME-independent)
        self.bind("<Delete>",    lambda e: self._kb_delete())
        self.bind("<Escape>",        lambda e: self._deselect())
        self.bind("<Left>",          lambda e: self._nudge(-10, 0))
        self.bind("<Right>",         lambda e: self._nudge(10, 0))
        self.bind("<Up>",            lambda e: self._nudge(0, -10))
        self.bind("<Down>",          lambda e: self._nudge(0, 10))
        self.bind("<Shift-Left>",    lambda e: self._nudge(-1, 0))
        self.bind("<Shift-Right>",   lambda e: self._nudge(1, 0))
        self.bind("<Shift-Up>",      lambda e: self._nudge(0, -1))
        self.bind("<Shift-Down>",    lambda e: self._nudge(0, 1))

        # ── Sidebar ──
        right = ctk.CTkFrame(self, width=340)
        right.pack(side="left", fill="y", padx=(0, 12), pady=12)
        right.pack_propagate(False)

        # Bottom buttons — packed FIRST (2 rows) so they always get space
        bottom = ctk.CTkFrame(right, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=8, pady=8)

        b_row1 = ctk.CTkFrame(bottom, fg_color="transparent")
        b_row1.pack(fill="x", pady=(0, 4))
        ctk.CTkButton(b_row1, text="💾 Save Preset", width=155,
                      command=self._save_preset).pack(side="left")
        self._load_btn = ctk.CTkButton(b_row1, text="📂 Load Preset", width=155,
                                       command=self._show_preset_menu)
        self._load_btn.pack(side="right")

        b_row2 = ctk.CTkFrame(bottom, fg_color="transparent")
        b_row2.pack(fill="x")
        ctk.CTkButton(b_row2, text="🗑 Delete", fg_color="gray40", width=155,
                      command=self._delete_selected).pack(side="left")
        ctk.CTkButton(b_row2, text="✅ Save Overlays", width=155,
                      command=self._save).pack(side="right")

        add_row = ctk.CTkFrame(right, fg_color="transparent")
        add_row.pack(fill="x", padx=8, pady=(8, 2))
        ctk.CTkButton(add_row, text="+ Text",  width=120, command=self._add_text).pack(side="left", padx=(0, 4))
        ctk.CTkButton(add_row, text="+ Image", width=120, command=self._add_image).pack(side="left")

        ctk.CTkLabel(right, text="Elements", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=8, pady=(6, 2))
        self._elem_list = ctk.CTkScrollableFrame(right, height=80)
        self._elem_list.pack(fill="x", padx=8)

        ctk.CTkLabel(right, text="Properties", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=8, pady=(8, 2))
        self._props_frame = ctk.CTkScrollableFrame(right)
        self._props_frame.pack(fill="both", expand=True, padx=8)

    # ── Ratio ─────────────────────────────────────────────────────────────────

    def _apply_ratio(self, ratio: str, init: bool = False):
        self._ratio = ratio
        spec = RATIO_SPECS[ratio]
        self._cw, self._ch = spec["cw"], spec["ch"]
        self._rw, self._rh = spec["rw"], spec["rh"]
        self._canvas.config(width=self._cw, height=self._ch)
        self.geometry(spec["win"])
        ref = "1080×1920" if ratio == "9:16" else "1920×1080"
        self._hint_label.configure(
            text=f"Preview ({ref} → {self._cw}×{self._ch})  |  drag  |  Shift = straight line")
        for r, btn in self._ratio_btns.items():
            btn.configure(fg_color="steelblue" if r == ratio else ("gray30", "gray30"))
        if not init:
            self._redraw()

    def _to_canvas(self, rx, ry):
        return int(rx * self._cw / self._rw), int(ry * self._ch / self._rh)

    def _to_ref(self, cx, cy):
        return int(cx * self._rw / self._cw), int(cy * self._rh / self._ch)

    # ── Add elements ──────────────────────────────────────────────────────────

    def _add_text(self):
        fonts = _get_fonts()
        default_font = "Tahoma" if "Tahoma" in fonts else (fonts[0] if fonts else "Arial")
        elem = TextOverlay(text="ข้อความ", x=200, y=200, font_family=default_font)
        self._overlays.append(elem)
        self._select_elem(elem)

    def _add_image(self):
        path = filedialog.askopenfilename(
            title="Select Image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.gif"), ("All", "*.*")],
            parent=self)
        if not path:
            return
        try:
            img = Image.open(path)
            w, h = img.size
            if w > 400:
                h = int(h * 400 / w); w = 400
        except Exception:
            w, h = 300, 200
        elem = ImageOverlay(path=path, x=200, y=200, width=w, height=h)
        self._overlays.append(elem)
        self._select_elem(elem)

    def _delete_selected(self):
        if not self._selected:
            return
        uid = self._selected
        self._overlays = [e for e in self._overlays if e.uid != uid]
        self._selected = None
        self._refresh_list()
        self._clear_props()
        self._redraw()

    # ── Presets ───────────────────────────────────────────────────────────────

    def _save_preset(self):
        name = simpledialog.askstring("Save Preset", "Preset name:", parent=self)
        if not name:
            return
        PRESET_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "ratio": self._ratio,
            "overlays": [asdict(e) for e in self._overlays],
        }
        path = PRESET_DIR / f"{name}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        messagebox.showinfo("Saved", f"Preset '{name}' saved.", parent=self)

    def _show_preset_menu(self):
        """Show dropdown popup listing all saved presets."""
        PRESET_DIR.mkdir(parents=True, exist_ok=True)
        presets = sorted(PRESET_DIR.glob("*.json"))
        if not presets:
            messagebox.showinfo("No Presets", "No saved presets found.\nUse '💾 Save Preset' first.", parent=self)
            return
        import tkinter as _tk
        menu = _tk.Menu(self, tearoff=0)
        for p in presets:
            menu.add_command(label=p.stem, command=lambda path=p: self._load_preset_file(path))
        # Show below the button
        btn = self._load_btn
        x = btn.winfo_rootx()
        y = btn.winfo_rooty() + btn.winfo_height()
        menu.tk_popup(x, y)

    def _load_preset_file(self, path: Path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._overlays = [_overlay_from_dict(d) for d in data.get("overlays", [])]
            self._apply_ratio(data.get("ratio", self._ratio))
            self._selected = None
            self._refresh_list()
            self._clear_props()
            self._redraw()
        except Exception as e:
            messagebox.showerror("Load Failed", str(e), parent=self)

    # ── Selection ─────────────────────────────────────────────────────────────

    def _select_elem(self, elem):
        self._selected = elem.uid
        self._refresh_list()
        self._show_props(elem)
        self._redraw()

    def _refresh_list(self):
        for w in self._elem_list.winfo_children():
            w.destroy()
        for elem in self._overlays:
            label = ("T  " + elem.text[:20]) if elem.type == "text" else ("I  " + Path(elem.path).name[:20])
            is_sel = elem.uid == self._selected
            ctk.CTkButton(
                self._elem_list, text=label, anchor="w", height=26,
                fg_color=("steelblue", "steelblue") if is_sel else ("gray28", "gray28"),
                command=lambda e=elem: self._select_elem(e),
            ).pack(fill="x", pady=1)

    # ── Properties ────────────────────────────────────────────────────────────

    def _clear_props(self):
        for w in self._props_frame.winfo_children():
            w.destroy()

    def _show_props(self, elem):
        self._clear_props()
        pad = {"padx": 4, "pady": 2}

        if elem.type == "text":
            # Text content — Textbox for multiline (Enter = new line)
            ctk.CTkLabel(self._props_frame, text="Text  (Enter = new line)").pack(anchor="w", **pad)
            txt_box = ctk.CTkTextbox(self._props_frame, height=70, wrap="word")
            txt_box.insert("1.0", elem.text)
            txt_box.pack(fill="x", **pad)

            def _on_text_change(e, el=elem, tb=txt_box):
                el.text = tb.get("1.0", "end-1c")
                self._redraw()

            txt_box.bind("<KeyRelease>", _on_text_change)

            # Font family
            ctk.CTkLabel(self._props_frame, text="Font (Thai รองรับ)").pack(anchor="w", **pad)
            fv = ctk.StringVar(value=elem.font_family)
            font_list = _get_fonts()
            font_menu = ctk.CTkComboBox(
                self._props_frame, variable=fv, values=font_list, width=260,
                command=lambda v: self._set(elem, "font_family", v) or self._redraw())
            font_menu.pack(fill="x", **pad)

            # Font size
            ctk.CTkLabel(self._props_frame, text="Font Size").pack(anchor="w", **pad)
            sv = ctk.StringVar(value=str(elem.font_size))
            sv.trace_add("write", lambda *_: self._set_int(elem, "font_size", sv.get()))
            ctk.CTkEntry(self._props_frame, textvariable=sv, width=80).pack(anchor="w", **pad)

            # Color
            ctk.CTkLabel(self._props_frame, text="Color").pack(anchor="w", **pad)
            self._color_btn = ctk.CTkButton(
                self._props_frame, text=elem.color, height=28,
                fg_color=elem.color if self._valid_color(elem.color) else "gray30",
                command=lambda e=elem: self._pick_color(e))
            self._color_btn.pack(fill="x", **pad)

            # Bold
            bv = ctk.BooleanVar(value=elem.bold)
            bv.trace_add("write", lambda *_: self._set(elem, "bold", bv.get()) or self._redraw())
            ctk.CTkCheckBox(self._props_frame, text="Bold", variable=bv).pack(anchor="w", **pad)

            # Alignment buttons
            ctk.CTkLabel(self._props_frame, text="Align").pack(anchor="w", **pad)
            align_row = ctk.CTkFrame(self._props_frame, fg_color="transparent")
            align_row.pack(fill="x", **pad)
            for a, label in (("left", "◀ Left"), ("center", "— Center"), ("right", "Right ▶")):
                ctk.CTkButton(
                    align_row, text=label, width=82, height=26,
                    fg_color="steelblue" if elem.align == a else ("gray30", "gray30"),
                    command=lambda al=a, e=elem: self._set_align(e, al),
                ).pack(side="left", padx=1)

            # Center snap
            ctk.CTkButton(
                self._props_frame, text="⊕ Snap to Center", height=28,
                command=lambda e=elem: self._snap_center(e),
            ).pack(fill="x", **pad)

        else:
            ctk.CTkLabel(self._props_frame, text=Path(elem.path).name,
                         text_color="gray60", wraplength=260).pack(anchor="w", **pad)
            wh = ctk.CTkFrame(self._props_frame, fg_color="transparent")
            wh.pack(fill="x", **pad)
            ctk.CTkLabel(wh, text="W", width=18).pack(side="left")
            wv = ctk.StringVar(value=str(elem.width))
            wv.trace_add("write", lambda *_: self._set_int(elem, "width", wv.get()))
            ctk.CTkEntry(wh, textvariable=wv, width=70).pack(side="left", padx=2)
            ctk.CTkLabel(wh, text="H", width=18).pack(side="left")
            hv = ctk.StringVar(value=str(elem.height))
            hv.trace_add("write", lambda *_: self._set_int(elem, "height", hv.get()))
            ctk.CTkEntry(wh, textvariable=hv, width=70).pack(side="left", padx=2)

        # X / Y
        xy = ctk.CTkFrame(self._props_frame, fg_color="transparent")
        xy.pack(fill="x", **pad)
        ctk.CTkLabel(xy, text="X", width=18).pack(side="left")
        self._xv = ctk.StringVar(value=str(elem.x))
        self._xv.trace_add("write", lambda *_: self._set_int(elem, "x", self._xv.get()))
        ctk.CTkEntry(xy, textvariable=self._xv, width=70).pack(side="left", padx=2)
        ctk.CTkLabel(xy, text="Y", width=18).pack(side="left")
        self._yv = ctk.StringVar(value=str(elem.y))
        self._yv.trace_add("write", lambda *_: self._set_int(elem, "y", self._yv.get()))
        ctk.CTkEntry(xy, textvariable=self._yv, width=70).pack(side="left", padx=2)

    def _set_align(self, elem, align: str):
        elem.align = align
        self._show_props(elem)
        self._redraw()

    def _snap_center(self, elem):
        elem.x = self._rw // 2
        elem.align = "center"
        if hasattr(self, "_xv"):
            self._xv.set(str(elem.x))
        self._show_props(elem)
        self._redraw()

    def _set(self, elem, attr, val):
        setattr(elem, attr, val)

    def _set_int(self, elem, attr, val):
        try:
            setattr(elem, attr, int(val))
            self._redraw()
        except ValueError:
            pass

    def _pick_color(self, elem):
        result = colorchooser.askcolor(color=elem.color, parent=self)
        color = result[1]
        if color:
            elem.color = color
            self._color_btn.configure(text=color,
                                      fg_color=color if self._valid_color(color) else "gray30")
            self._redraw()

    @staticmethod
    def _valid_color(c: str) -> bool:
        return c.startswith("#") and len(c) in (4, 7)

    # ── Mouse drag ────────────────────────────────────────────────────────────

    def _text_canvas_x(self, elem) -> int:
        """Canvas X position for text drawing, accounting for alignment."""
        if getattr(elem, "align", "left") == "center":
            return self._cw // 2
        elif getattr(elem, "align", "left") == "right":
            return self._cw - self._to_canvas(elem.x, 0)[0]
        return self._to_canvas(elem.x, elem.y)[0]

    def _text_bounds(self, elem) -> tuple:
        """Return (canvas_x, line_w, total_h) for a text element."""
        fs = max(8, int(elem.font_size * self._cw / self._rw))
        lines = elem.text.split("\n")
        n_lines = max(1, len(lines))
        max_chars = max((len(l) for l in lines), default=1)
        w = max(20, int(max_chars * fs * 0.62))
        h = int(n_lines * fs * 1.4)
        align = getattr(elem, "align", "left")
        tx = self._text_canvas_x(elem)
        if align == "center":
            tx -= w // 2
        elif align == "right":
            tx -= w
        return tx, w, h

    def _hit_test(self, cx: int, cy: int) -> Optional[str]:
        for elem in reversed(self._overlays):
            if elem.type == "text":
                tx, w, h = self._text_bounds(elem)
                _, ey = self._to_canvas(elem.x, elem.y)
            else:
                tx, ey = self._to_canvas(elem.x, elem.y)
                ecx, ecy = self._to_canvas(elem.x + elem.width, elem.y + elem.height)
                w, h = ecx - tx, ecy - ey
            if tx <= cx <= tx + w and ey <= cy <= ey + h:
                return elem.uid
        return None

    def _on_press(self, event):
        uid = self._hit_test(event.x, event.y)
        self._shift_axis = None
        if uid:
            self._selected = uid
            elem = self._get(uid)
            self._drag_start = (event.x, event.y, elem.x, elem.y)
            self._refresh_list()
            self._show_props(elem)
        else:
            self._selected = None
            self._drag_start = None
            self._refresh_list()
            self._clear_props()
        self._redraw()

    def _on_drag(self, event):
        if not self._drag_start or not self._selected:
            return
        sx, sy, ox, oy = self._drag_start
        dx_c = event.x - sx
        dy_c = event.y - sy

        if event.state & 0x0001:
            if self._shift_axis is None and (abs(dx_c) > 5 or abs(dy_c) > 5):
                self._shift_axis = "h" if abs(dx_c) >= abs(dy_c) else "v"
            if self._shift_axis == "h":
                dy_c = 0
            elif self._shift_axis == "v":
                dx_c = 0
        else:
            self._shift_axis = None

        dx_r, dy_r = self._to_ref(dx_c, dy_c)
        elem = self._get(self._selected)
        elem.x = max(0, ox + dx_r)
        elem.y = max(0, oy + dy_r)
        if hasattr(self, "_xv"):
            self._xv.set(str(elem.x))
        if hasattr(self, "_yv"):
            self._yv.set(str(elem.y))
        self._redraw()

    def _on_release(self, event):
        self._drag_start = None
        self._shift_axis = None

    def _kb_delete(self):
        """Delete selected element only when focus is NOT on a text input."""
        focused = self.focus_get()
        # Skip if a text widget (CTkTextbox inner widget or Entry) has focus
        if focused and focused.winfo_class() in ("Text", "Entry", "TEntry"):
            return
        self._delete_selected()

    def _deselect(self):
        self._selected = None
        self._refresh_list()
        self._clear_props()
        self._redraw()

    def _nudge(self, dx_r: int, dy_r: int):
        """Move selected element by (dx_r, dy_r) in reference pixels."""
        if not self._selected:
            return
        elem = self._get(self._selected)
        elem.x = max(0, elem.x + dx_r)
        elem.y = max(0, elem.y + dy_r)
        if hasattr(self, "_xv"):
            self._xv.set(str(elem.x))
        if hasattr(self, "_yv"):
            self._yv.set(str(elem.y))
        self._redraw()

    def _get(self, uid: str):
        return next(e for e in self._overlays if e.uid == uid)

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _redraw(self):
        self._canvas.delete("all")
        self._img_cache.clear()

        for i in range(11):
            x = int(i * self._cw / 10)
            self._canvas.create_line(x, 0, x, self._ch, fill="#1e1e1e")
        for i in range(11):
            y = int(i * self._ch / 10)
            self._canvas.create_line(0, y, self._cw, y, fill="#1e1e1e")
        self._canvas.create_line(self._cw // 2, 0, self._cw // 2, self._ch, fill="#252525", dash=(2, 4))
        self._canvas.create_line(0, self._ch // 2, self._cw, self._ch // 2, fill="#252525", dash=(2, 4))

        for elem in self._overlays:
            is_sel = elem.uid == self._selected
            _, cy = self._to_canvas(elem.x, elem.y)
            cx, _ = self._to_canvas(elem.x, elem.y)

            if elem.type == "text":
                fs = max(7, int(elem.font_size * self._cw / self._rw))
                weight = "bold" if elem.bold else "normal"
                fill = elem.color if self._valid_color(elem.color) else "white"
                font_tk = (elem.font_family, fs, weight)
                align = getattr(elem, "align", "left")

                if align == "center":
                    draw_x = self._cw // 2
                    anchor = "n"
                    justify = "center"
                elif align == "right":
                    draw_x = self._cw - self._to_canvas(elem.x, 0)[0]
                    anchor = "ne"
                    justify = "right"
                else:
                    draw_x = cx
                    anchor = "nw"
                    justify = "left"

                self._canvas.create_text(draw_x, cy, text=elem.text, fill=fill,
                                          font=font_tk, anchor=anchor, justify=justify)
                if is_sel:
                    bx, w, h = self._text_bounds(elem)
                    self._canvas.create_rectangle(bx - 1, cy - 1, bx + w + 1, cy + h + 1,
                                                   outline="#29b6f6", width=1, dash=(4, 3))

            elif elem.type == "image":
                if Path(elem.path).exists():
                    try:
                        ecx, ecy = self._to_canvas(elem.x + elem.width, elem.y + elem.height)
                        pw, ph = max(1, ecx - cx), max(1, ecy - cy)
                        img = Image.open(elem.path).resize((pw, ph), Image.LANCZOS)
                        photo = ImageTk.PhotoImage(img)
                        self._img_cache[elem.uid] = photo
                        self._canvas.create_image(cx, cy, image=photo, anchor="nw")
                        if is_sel:
                            self._canvas.create_rectangle(cx, cy, cx + pw, cy + ph,
                                                           outline="#29b6f6", width=1, dash=(4, 3))
                    except Exception:
                        self._canvas.create_rectangle(cx, cy, cx + 60, cy + 40, fill="#333", outline="#f44")
                else:
                    self._canvas.create_rectangle(cx, cy, cx + 80, cy + 50,
                                                   fill="#2a1a1a", outline="#f44", dash=(3, 3))
                    self._canvas.create_text(cx + 4, cy + 4, text="missing", fill="#f44",
                                              font=("Arial", 8), anchor="nw")

        if self._shift_axis and self._selected:
            elem = self._get(self._selected)
            cx, cy = self._to_canvas(elem.x, elem.y)
            if self._shift_axis == "h":
                self._canvas.create_line(0, cy, self._cw, cy, fill="#29b6f6", dash=(6, 3), width=1)
            else:
                self._canvas.create_line(cx, 0, cx, self._ch, fill="#29b6f6", dash=(6, 3), width=1)

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self):
        self.task.overlays = list(self._overlays)
        self.task.overlay_ratio = self._ratio
        self.destroy()
