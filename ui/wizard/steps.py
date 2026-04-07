"""Wizard step frames: Directories, Images, Tags/Captions, Finalize."""

import customtkinter as ctk
import tkinter as tk
from pathlib import Path
from typing import Optional, Callable, List
from tkinter import filedialog, messagebox
import queue
import threading

from PIL import Image, ImageTk
from core.session import get_session
from core.config import VALID_EXTENSIONS
from core.data.profiles import get_profiles_manager
from core.data.file_handler import load_image_files
from core.ai.vram import get_vram_manager, State
from core.ai.tagger import tag_image, get_tagger
from core.ai.captioner import generate_caption
import core.config as core_config
from ui.caption_prompt_presets_ui import build_preset_row
from ui.tooltip import add_tooltip

# Step 3 master tag list: cap rows so the UI stays responsive (filter narrows further)
MASTER_TAG_MAX_RENDER = 500

# Profile keys / UI labels for master tag pool (union across session)
MASTER_TAG_LIST_MODE_SCANNED_KEY = "scanned"
MASTER_TAG_LIST_MODE_FULL_KEY = "full"
MASTER_TAG_LIST_MODE_SCANNED_UI = "Scanned tags (WD14)"
MASTER_TAG_LIST_MODE_FULL_UI = "All session tags"


def _normalize_master_tag_list_mode_key(raw) -> str:
    """Map profile value to scanned|full (tolerates legacy or odd casing)."""
    if raw == MASTER_TAG_LIST_MODE_FULL_KEY:
        return MASTER_TAG_LIST_MODE_FULL_KEY
    if not isinstance(raw, str):
        return MASTER_TAG_LIST_MODE_SCANNED_KEY
    s = raw.strip().lower()
    if s in (MASTER_TAG_LIST_MODE_FULL_KEY, "all", "all_session", "all session"):
        return MASTER_TAG_LIST_MODE_FULL_KEY
    return MASTER_TAG_LIST_MODE_SCANNED_KEY


def _schedule_main(callback):
    """Run callback on the Tk main loop (safe to call from a worker thread)."""
    from ui.app_main import get_app
    app = get_app()
    if app is not None:
        app.root.after(0, callback)


def _make_zoom_pan_canvas(parent, width: int = 320, height: int = 320) -> tk.Canvas:
    """Return a tk.Canvas with mouse-wheel zoom and click-drag pan built in.

    Usage:
        canvas = _make_zoom_pan_canvas(parent, 400, 400)
        canvas.load_image(pil_image)   # resets zoom/pan and draws the image
    """
    canvas = tk.Canvas(parent, width=width, height=height,
                       bg="#1a1a1a", highlightthickness=0, cursor="fleur")
    canvas._img_full = None      # PIL Image (full resolution)
    canvas._photo = None         # ImageTk.PhotoImage kept alive
    canvas._zoom = 1.0
    canvas._pan = [0, 0]
    canvas._drag_start = [0, 0]

    def _redraw():
        if canvas._img_full is None:
            return
        w = max(1, int(canvas._img_full.width * canvas._zoom))
        h = max(1, int(canvas._img_full.height * canvas._zoom))
        resized = canvas._img_full.resize((w, h), Image.Resampling.LANCZOS)
        canvas._photo = ImageTk.PhotoImage(resized)
        canvas.delete("all")
        canvas.create_image(canvas._pan[0], canvas._pan[1],
                            anchor="nw", image=canvas._photo)

    def _on_zoom(event):
        delta = 1.1 if (event.delta > 0 or getattr(event, "num", 0) == 4) else 1 / 1.1
        canvas._zoom = max(0.1, min(10.0, canvas._zoom * delta))
        _redraw()

    def _on_press(event):
        canvas._drag_start = [event.x, event.y]

    def _on_drag(event):
        canvas._pan[0] += event.x - canvas._drag_start[0]
        canvas._pan[1] += event.y - canvas._drag_start[1]
        canvas._drag_start = [event.x, event.y]
        _redraw()

    canvas.bind("<MouseWheel>", _on_zoom)
    canvas.bind("<Button-4>", _on_zoom)
    canvas.bind("<Button-5>", _on_zoom)
    canvas.bind("<ButtonPress-1>", _on_press)
    canvas.bind("<B1-Motion>", _on_drag)

    def load_image(pil_image: Image.Image) -> None:
        canvas._img_full = pil_image.convert("RGB")
        canvas._zoom = 1.0
        canvas._pan = [0, 0]
        _redraw()

    def clear_image(placeholder: str = "") -> None:
        canvas._img_full = None
        canvas._photo = None
        canvas.delete("all")
        if placeholder:
            cw = canvas.winfo_width() or width
            ch = canvas.winfo_height() or height
            canvas.create_text(cw // 2, ch // 2, text=placeholder,
                               fill="#888888", font=("TkDefaultFont", 10))

    canvas.load_image = load_image
    canvas.clear_image = clear_image
    canvas._redraw = _redraw
    return canvas


def _drop_zone(parent, label: str, browse_callback: Callable[[], None], **kwargs) -> ctk.CTkFrame:
    """Create a labeled drop zone frame with Browse button."""
    f = ctk.CTkFrame(parent, **kwargs)
    ctk.CTkLabel(f, text=label, font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=10, pady=(10, 5))
    inner = ctk.CTkFrame(f, fg_color="transparent")
    inner.pack(fill="x", padx=10, pady=(0, 10))
    ctk.CTkButton(inner, text="Browse…", width=100, command=browse_callback).pack(side="left", padx=(0, 10))
    path_label = ctk.CTkLabel(inner, text="(none)", anchor="w")
    path_label.pack(side="left", fill="x", expand=True)
    f._path_label = path_label
    return f


class StepDirectories(ctk.CTkFrame):
    """Step 1: Set source and output directories (drag folder or Browse)."""
    def __init__(self, parent, on_paths_changed: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.on_paths_changed = on_paths_changed
        self.session = get_session()
        self.profiles = get_profiles_manager()
        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(self, text="Set source and output folders. You can drag a folder here or click Browse.",
                     font=ctk.CTkFont(size=12)).pack(anchor="w", padx=10, pady=(10, 5))
        self.source_zone = _drop_zone(self, "Source folder", self._browse_source)
        self.source_zone.pack(fill="x", padx=10, pady=5)
        add_tooltip(self.source_zone.winfo_children()[1].winfo_children()[0],
                    "Select the folder containing your original images")
        self.output_zone = _drop_zone(self, "Output folder", self._browse_output)
        self.output_zone.pack(fill="x", padx=10, pady=5)
        add_tooltip(self.output_zone.winfo_children()[1].winfo_children()[0],
                    "Select the folder where cropped/processed images will be saved")
        self._refresh_labels()

    def _browse_source(self):
        folder = filedialog.askdirectory(title="Select Source Folder")
        if folder:
            self._set_source(Path(folder))

    def _browse_output(self):
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self._set_output(Path(folder))

    def _set_source(self, p: Path):
        self.session.source_folder = p
        self.session.processed_folder = p / "processed"
        self.profiles.set_folders(str(p), None)
        self._refresh_labels()
        if self.on_paths_changed:
            self.on_paths_changed()

    def _set_output(self, p: Path):
        self.session.output_folder = p
        self.profiles.set_folders(None, str(p))
        self._refresh_labels()
        if self.on_paths_changed:
            self.on_paths_changed()

    def _refresh_labels(self):
        self.source_zone._path_label.configure(text=str(self.session.source_folder) if self.session.source_folder else "(none)")
        self.output_zone._path_label.configure(text=str(self.session.output_folder) if self.session.output_folder else "(none)")

    def on_drop(self, paths: List[Path]) -> bool:
        """Handle dropped paths. If single folder, set as source then output (alternating). Returns True if handled."""
        if not paths:
            return False
        for p in paths:
            if p.is_dir():
                if not self.session.source_folder:
                    self._set_source(p)
                    return True
                if not self.session.output_folder:
                    self._set_output(p)
                    return True
                self._set_output(p)
                return True
        return False


class StepImages(ctk.CTkFrame):
    """Step 2: Add/remove/rename images in session."""
    def __init__(self, parent, on_list_changed: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.on_list_changed = on_list_changed
        self.session = get_session()
        self._listbox_frame = None
        self._listbox = None
        self._build_ui()

    def _build_ui(self):
        # Row 0: full-width toolbar (buttons constrain its own height, not column widths)
        # Row 1: two-column area — list (weight=1) | preview (weight=2)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=2)

        # -- Top bar spanning both columns --
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 0))
        ctk.CTkLabel(top_frame, text="Add images by dragging files here or using the buttons below.",
                     font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(0, 5))
        btn_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=5)
        _add_src_btn = ctk.CTkButton(btn_frame, text="Add from source folder", width=160, command=self._add_from_source)
        _add_src_btn.pack(side="left", padx=(0, 5))
        add_tooltip(_add_src_btn, "Load all supported images from the configured source folder")
        _add_files_btn = ctk.CTkButton(btn_frame, text="Add files…", width=100, command=self._add_files)
        _add_files_btn.pack(side="left", padx=(0, 5))
        add_tooltip(_add_files_btn, "Browse and pick individual image files to add to the session")
        _remove_btn = ctk.CTkButton(btn_frame, text="Remove", width=100, command=self._remove_selected)
        _remove_btn.pack(side="left", padx=(0, 5))
        add_tooltip(_remove_btn, "Remove selected images from the session (does not delete files on disk)")
        ctk.CTkLabel(top_frame, text="Click an image to select it; Ctrl+click for multiple. Use the Batch Rename tab to rename source files.",
                     font=ctk.CTkFont(size=11), text_color="gray70").pack(anchor="w", pady=(2, 4))

        # -- Left column: image list only --
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=1, column=0, sticky="nsew", padx=(10, 0), pady=(0, 5))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(0, weight=1)
        self._listbox_frame = ctk.CTkScrollableFrame(left)
        self._listbox_frame.grid(row=0, column=0, sticky="nsew")
        self._selected_indices: set = set()

        # -- Right column: preview --
        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=1, column=1, sticky="nsew", padx=(5, 10), pady=(0, 5))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(right, text="Preview  (scroll to zoom · drag to pan)",
                     font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", pady=(0, 5))
        self._preview_canvas = _make_zoom_pan_canvas(right, width=400, height=400)
        self._preview_canvas.grid(row=1, column=0, sticky="nsew")
        self._preview_canvas.clear_image("Click an image to preview.")
        btn_row = ctk.CTkFrame(right, fg_color="transparent")
        btn_row.grid(row=2, column=0, pady=(5, 0))
        _pop_btn2 = ctk.CTkButton(btn_row, text="Preview in window", width=140,
                                  command=self._open_preview_window)
        _pop_btn2.pack(side="left", padx=(0, 5))
        add_tooltip(_pop_btn2, "Open a resizable pop-out with zoom and pan (scroll to zoom, drag to pan)")
        _reset_btn2 = ctk.CTkButton(btn_row, text="Reset zoom", width=90,
                                    command=lambda: self._preview_canvas._redraw())
        _reset_btn2.pack(side="left")
        add_tooltip(_reset_btn2, "Reset zoom and pan to the original view")
        self._refresh_list()

    def _add_from_source(self):
        n = self.session.add_from_source_folder()
        self._refresh_list()
        if n > 0 and self.on_list_changed:
            self.on_list_changed()

    def _batch_prefix(self):
        prefix = (self._prefix_entry.get() or "").strip()
        if not prefix:
            messagebox.showinfo("Batch prefix", "Enter a prefix first.")
            return
        for i in range(len(self.session.items)):
            item = self.session.get_item(i)
            if item:
                item.output_stem = prefix + item.get_output_stem()
        self._refresh_list()
        if self.on_list_changed:
            self.on_list_changed()

    def _batch_suffix(self):
        suffix = (self._suffix_entry.get() or "").strip()
        if not suffix:
            messagebox.showinfo("Batch suffix", "Enter a suffix first.")
            return
        for i in range(len(self.session.items)):
            item = self.session.get_item(i)
            if item:
                item.output_stem = item.get_output_stem() + suffix
        self._refresh_list()
        if self.on_list_changed:
            self.on_list_changed()

    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="Add images",
            filetypes=[("Images", " ".join("*" + e for e in VALID_EXTENSIONS))]
        )
        if paths:
            added = self.session.add_items([Path(p) for p in paths])
            self._refresh_list()
            if self.on_list_changed:
                self.on_list_changed()
            if added:
                messagebox.showinfo("Add files", f"Added {added} image(s).")

    def _get_selected_list(self) -> List[int]:
        """Return sorted list of selected indices (for remove_indices etc.)."""
        return sorted(self._selected_indices)

    def _on_row_click(self, index: int, event):
        """Handle click on a list row: plain click = select only this; Ctrl+click = toggle."""
        if event.state & 0x4:  # Ctrl
            if index in self._selected_indices:
                self._selected_indices.discard(index)
            else:
                self._selected_indices.add(index)
        else:
            self._selected_indices = {index}
        self._refresh_list()

    def _remove_selected(self):
        sel = self._get_selected_list()
        if not sel:
            messagebox.showinfo("Remove", "Select one or more images first.")
            return
        max_i = len(self.session.items) - 1
        sel = [i for i in sel if 0 <= i <= max_i]
        if not sel:
            return
        self.session.remove_indices(sel)
        self._selected_indices = set()
        self._refresh_list()
        if self.on_list_changed:
            self.on_list_changed()

    def _rename_selected(self):
        sel = self._get_selected_list()
        if len(sel) != 1:
            messagebox.showinfo("Rename", "Select exactly one image to rename.")
            return
        item = self.session.get_item(sel[0])
        if not item:
            return
        from tkinter import simpledialog
        name = simpledialog.askstring("Rename", "Output filename (without extension):", initialvalue=item.get_output_stem())
        if name:
            self.session.rename_item(sel[0], name)
            self._refresh_list()
            if self.on_list_changed:
                self.on_list_changed()

    def _refresh_list(self):
        """Rebuild the clickable list of image rows and update preview."""
        for w in self._listbox_frame.winfo_children():
            w.destroy()
        if not self.session.items:
            empty = ctk.CTkLabel(self._listbox_frame, text="No images. Add from source or add files.", text_color="gray60")
            empty.pack(anchor="w", pady=5)
            self._update_preview()
            return
        max_i = len(self.session.items) - 1
        self._selected_indices = {i for i in self._selected_indices if 0 <= i <= max_i}
        for i, item in enumerate(self.session.items):
            stem = item.get_output_stem()
            line = f"  {i+1}. {item.original_path.name}  →  {stem}"
            is_selected = i in self._selected_indices
            row = ctk.CTkFrame(
                self._listbox_frame,
                fg_color=("gray75", "gray30") if is_selected else "transparent",
                corner_radius=4,
                cursor="hand2"
            )
            row.pack(fill="x", pady=2)
            lbl = ctk.CTkLabel(row, text=line, anchor="w")
            lbl.pack(fill="x", padx=8, pady=4)
            lbl.bind("<Button-1>", lambda e, idx=i: self._on_row_click(idx, e))
            row.bind("<Button-1>", lambda e, idx=i: self._on_row_click(idx, e))
        self._update_preview()

    def _update_preview(self):
        """Load selected image into the zoom/pan canvas."""
        sel = self._get_selected_list()
        idx = sel[0] if sel else None
        if idx is None or idx < 0 or idx >= len(self.session.items):
            self._preview_canvas.clear_image("Click an image to preview.")
            return
        item = self.session.get_item(idx)
        if not item or not item.original_path.exists():
            self._preview_canvas.clear_image("Image not found.")
            return
        try:
            image = Image.open(item.original_path).convert("RGB")
            self._preview_canvas.load_image(image)
        except Exception:
            self._preview_canvas.clear_image("Could not load image.")

    def _open_preview_window(self):
        """Open a resizable pop-out with zoom/pan for the first selected image."""
        sel = self._get_selected_list()
        idx = sel[0] if sel else None
        if idx is None or idx < 0 or idx >= len(self.session.items):
            messagebox.showinfo("Preview", "Select an image first.")
            return
        item = self.session.get_item(idx)
        if not item or not item.original_path.exists():
            messagebox.showwarning("Preview", "Image file not found.")
            return
        try:
            image = Image.open(item.original_path).convert("RGB")
        except Exception as e:
            messagebox.showerror("Preview", str(e))
            return
        win = ctk.CTkToplevel(self.winfo_toplevel())
        win.title(f"Preview — #{idx + 1} {item.original_path.name}")
        win.transient(self.winfo_toplevel())
        cw = min(image.width, 900)
        ch = min(image.height, 700)
        win.geometry(f"{cw}x{ch + 60}")
        win.resizable(True, True)
        f = ctk.CTkFrame(win, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        canvas = _make_zoom_pan_canvas(f, width=cw, height=ch)
        canvas.pack(fill="both", expand=True)
        canvas.load_image(image)
        info = ctk.CTkLabel(win, text=f"#{idx + 1} — {item.original_path.name}  |  {image.width}×{image.height}px",
                            text_color="gray70")
        info.pack(pady=(4, 0))
        bot = ctk.CTkFrame(win, fg_color="transparent")
        bot.pack(pady=(4, 8))
        ctk.CTkButton(bot, text="Reset zoom", width=90,
                      command=lambda: canvas.load_image(image)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(bot, text="Close", width=80, command=win.destroy).pack(side="left")

    def on_drop(self, paths: List[Path]) -> bool:
        valid = [p for p in paths if p.is_file() and p.suffix.lower() in VALID_EXTENSIONS]
        if not valid:
            return False
        added = self.session.add_items(valid)
        self._refresh_list()
        if self.on_list_changed:
            self.on_list_changed()
        if added:
            messagebox.showinfo("Drop", f"Added {added} image(s).")
        return True


class StepCaptions(ctk.CTkFrame):
    """Step 3: Tags and captions for the selected image."""
    def __init__(self, parent, on_changed: Optional[Callable[[], None]] = None,
                 open_settings_cb: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.on_changed = on_changed
        self._open_settings_cb = open_settings_cb
        self.session = get_session()
        self.current_index: Optional[int] = None
        import threading as _threading
        self._caption_stop_event = _threading.Event()
        self._tags_stop_event = _threading.Event()
        self._tag_master_set: set = set()
        self._tags_panel_open = True
        self._caption_panel_open = True
        self._batch_ui_queue: queue.SimpleQueue = queue.SimpleQueue()
        self._batch_ui_polling = False
        self._master_tag_pool_use_full = False
        self._master_tag_list_menu: Optional[ctk.CTkOptionMenu] = None
        self._build_ui()

    def apply_profile(self, profile: dict) -> None:
        """Apply profile defaults (e.g. trigger words) to this step."""
        self.trigger_entry.delete(0, "end")
        self.trigger_entry.insert(0, profile.get("default_trigger_words") or "")
        fmt = profile.get("default_output_format", "Natural language")
        if fmt in ("Tags only", "Natural language", "Both"):
            self.output_format_var.set(fmt)
        self.session.set_output_format(self.output_format_var.get())
        if hasattr(self, "system_prompt_text"):
            self._load_system_prompt_from_profile()
        if hasattr(self, "_master_tag_list_mode_var"):
            self._apply_master_tag_list_mode_from_profile_dict(profile)

    def _apply_master_tag_list_mode_from_profile_dict(self, profile: dict) -> None:
        key = _normalize_master_tag_list_mode_key(profile.get("master_tag_list_mode"))
        self._master_tag_pool_use_full = key == MASTER_TAG_LIST_MODE_FULL_KEY
        ui = (
            MASTER_TAG_LIST_MODE_FULL_UI if self._master_tag_pool_use_full
            else MASTER_TAG_LIST_MODE_SCANNED_UI
        )
        self._master_tag_list_mode_var.set(ui)
        menu = getattr(self, "_master_tag_list_menu", None)
        if menu is not None:
            try:
                menu.set(ui)
            except Exception:
                pass

    def _on_master_tag_list_mode_changed(self, choice: str) -> None:
        self._master_tag_pool_use_full = choice == MASTER_TAG_LIST_MODE_FULL_UI
        pm = get_profiles_manager()
        name = pm.config.get("current_profile", "User settings")
        # Always shallow-copy the full current profile — never save from load_profile(...) or {}
        # or a missing profile would wipe other keys.
        prof = dict(pm.get_current_profile())
        prof["master_tag_list_mode"] = (
            MASTER_TAG_LIST_MODE_FULL_KEY if self._master_tag_pool_use_full
            else MASTER_TAG_LIST_MODE_SCANNED_KEY
        )
        pm.save_profile(name, prof)
        self._build_tag_master_set()
        self._rebuild_tag_list()

    def _build_ui(self):
        # Top: hint + one general bar (session controls). Tag/caption actions live above each column.
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(top, text="Select an image (index), then generate or edit tags and caption.",
                     font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(0, 2))

        general_bar = ctk.CTkFrame(top, fg_color="transparent")
        general_bar.pack(fill="x", pady=(0, 2))
        self.index_var = ctk.StringVar(value="1")
        ctk.CTkLabel(general_bar, text="Image index:").pack(side="left", padx=(0, 5))
        _index_entry = ctk.CTkEntry(general_bar, textvariable=self.index_var, width=60)
        _index_entry.pack(side="left", padx=(0, 10))
        add_tooltip(_index_entry, "1-based index of the image to load from the session list")
        _load_btn = ctk.CTkButton(general_bar, text="Load", width=70, command=self._load_index)
        _load_btn.pack(side="left", padx=(0, 5))
        add_tooltip(_load_btn, "Load the image at the given index into the tag and caption editors")
        ctk.CTkLabel(general_bar, text="Tag threshold:").pack(side="left", padx=(10, 2))
        self.threshold_var = ctk.DoubleVar(value=0.5)
        _threshold_slider = ctk.CTkSlider(
            general_bar, from_=0.35, to=0.85, variable=self.threshold_var, width=80
        )
        _threshold_slider.pack(side="left", padx=2)
        add_tooltip(
            _threshold_slider,
            "Minimum confidence for a WD14 tag to be included (higher = fewer, more confident tags)",
        )
        self._btn_stop_caption = ctk.CTkButton(
            general_bar, text="Stop", width=60,
            fg_color="darkred", command=self._stop_captioning_batch,
        )
        add_tooltip(
            self._btn_stop_caption,
            "Stop batch captioning or tagging after the current image finishes. "
            "Already-completed work is kept.\n\n"
            "Tip: you can also open Settings and change 'Caption source' to 'local' "
            "to switch to a local model — it takes effect on the next image.",
        )
        self._btn_save_edits = ctk.CTkButton(
            general_bar, text="Save edits", width=90,
            fg_color="darkgreen", command=self._save_and_confirm,
        )
        self._btn_save_edits.pack(side="left", padx=(10, 5))
        add_tooltip(
            self._btn_save_edits,
            "Save the current tags and caption edits to the session (auto-saved when switching images)",
        )
        self._loading_label = ctk.CTkLabel(general_bar, text="", text_color="gray70")
        self._loading_label.pack(side="left", padx=(10, 0))
        ctk.CTkLabel(general_bar, text="Output:").pack(side="left", padx=(10, 2))
        self.output_format_var = ctk.StringVar(value="Natural language")
        om = ctk.CTkOptionMenu(
            general_bar, variable=self.output_format_var,
            values=["Tags only", "Natural language", "Both"], width=120,
        )
        om.pack(side="left", padx=2)
        add_tooltip(om, "Choose whether to write tags only, a natural-language caption, or both to the .txt sidecar")
        self.output_format_var.trace_add("write", lambda *a: self.session.set_output_format(self.output_format_var.get()))
        ctk.CTkLabel(general_bar, text="Trigger words:").pack(side="left", padx=(10, 2))
        self.trigger_entry = ctk.CTkEntry(general_bar, placeholder_text="e.g. mylora", width=100)
        self.trigger_entry.pack(side="left", padx=2)
        add_tooltip(self.trigger_entry, "Words prepended to every caption (e.g. your LoRA trigger token)")
        _export_btn = ctk.CTkButton(general_bar, text="Export .md", width=90, command=self._export_markdown)
        _export_btn.pack(side="left", padx=(10, 2))
        add_tooltip(
            _export_btn,
            "Export all session tags and captions to a Markdown file.\n"
            "Each entry is numbered and named after its source image.",
        )
        self._toolbar_general = general_bar

        # Main content area: left = list + preview, right = tags/caption editors
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=10, pady=5)
        # Left column (list+preview) fixed-ish, right column (editors) takes remaining space
        content.grid_columnconfigure(0, weight=0)
        content.grid_columnconfigure(1, weight=1)
        content.grid_rowconfigure(0, weight=1)

        # Left column: session images list + preview
        left = ctk.CTkFrame(content, fg_color="transparent", width=260)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        left.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(left, text="Session images", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", pady=(0, 5))
        self._listbox_frame_captions = ctk.CTkScrollableFrame(left)
        self._listbox_frame_captions.grid(row=1, column=0, sticky="nsew", pady=(0, 5))
        self._selected_index_caption: Optional[int] = None
        # Preview under the list
        preview_frame = ctk.CTkFrame(left, fg_color="transparent")
        preview_frame.grid(row=2, column=0, sticky="nsew")
        ctk.CTkLabel(preview_frame, text="Preview  (scroll·drag)",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 2))
        self._preview_canvas = _make_zoom_pan_canvas(preview_frame, width=240, height=240)
        self._preview_canvas.pack(fill="both", expand=True, pady=3)
        self._preview_canvas.clear_image("Select an image to preview.")
        btn_row3 = ctk.CTkFrame(preview_frame, fg_color="transparent")
        btn_row3.pack(pady=(3, 0))
        _pop_btn3 = ctk.CTkButton(btn_row3, text="Preview in window", width=140,
                                  command=self._open_preview_window)
        _pop_btn3.pack(side="left", padx=(0, 4))
        add_tooltip(_pop_btn3, "Open a resizable pop-out with zoom and pan (scroll to zoom, drag to pan)")
        _reset_btn3 = ctk.CTkButton(btn_row3, text="Reset zoom", width=80,
                                    command=lambda: self._preview_canvas._redraw())
        _reset_btn3.pack(side="left")
        add_tooltip(_reset_btn3, "Reset zoom and pan to the original view")

        # Right column: collapsible tags panel | collapsible caption+prompts (horizontal pack)
        right = ctk.CTkFrame(content, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        # ---- Tags panel (collapsible) ----
        self._tags_panel = ctk.CTkFrame(right, fg_color="transparent")
        self._tags_panel.pack(side="left", fill="both", expand=True)

        tags_action_row = ctk.CTkFrame(self._tags_panel, fg_color="transparent")
        tags_action_row.pack(fill="x", pady=(0, 4))
        self._btn_tags = ctk.CTkButton(tags_action_row, text="Generate tags", width=100, command=self._gen_tags)
        self._btn_tags.pack(side="left", padx=(0, 6))
        add_tooltip(self._btn_tags, "Run the WD14 tagger on this image")
        self._btn_batch_tags = ctk.CTkButton(tags_action_row, text="Batch tags (all)", width=120, command=self._batch_gen_tags)
        self._btn_batch_tags.pack(side="left", padx=(0, 4))
        add_tooltip(self._btn_batch_tags, "Tag every image in the session using WD14")

        tags_hdr = ctk.CTkFrame(self._tags_panel, fg_color="transparent")
        tags_hdr.pack(fill="x", pady=(0, 3))
        self._tags_toggle_btn = ctk.CTkButton(
            tags_hdr, text="◀", width=28, command=self._toggle_tags_panel
        )
        self._tags_toggle_btn.pack(side="left", padx=(0, 4))
        add_tooltip(self._tags_toggle_btn, "Collapse or expand the tags column")
        ctk.CTkLabel(tags_hdr, text="Tags",
                     font=ctk.CTkFont(weight="bold")).pack(side="left")
        self._tag_count_label = ctk.CTkLabel(tags_hdr, text="",
                                             text_color="gray60",
                                             font=ctk.CTkFont(size=11))
        self._tag_count_label.pack(side="left", padx=(6, 0))
        self._tag_filter_var = ctk.StringVar()
        self._tag_filter_var.trace_add("write", lambda *_: self._rebuild_tag_list())
        _filter_entry = ctk.CTkEntry(tags_hdr, textvariable=self._tag_filter_var,
                                     placeholder_text="Filter…", width=90)
        _filter_entry.pack(side="left", fill="x", expand=True, padx=(6, 4))
        add_tooltip(_filter_entry, "Type to filter visible tags in both lists")
        self._new_tag_entry = ctk.CTkEntry(tags_hdr, placeholder_text="New tag", width=72)
        self._new_tag_entry.pack(side="left", padx=(0, 3))
        self._new_tag_entry.bind("<Return>", lambda _e: self._add_manual_tag())
        _add_btn = ctk.CTkButton(tags_hdr, text="+", width=28, command=self._add_manual_tag)
        _add_btn.pack(side="left")
        add_tooltip(_add_btn, "Add a new tag to the current image and master list")

        self._tags_content = ctk.CTkFrame(self._tags_panel, fg_color="transparent")
        self._tags_content.pack(fill="both", expand=True)
        self._tags_content.grid_columnconfigure(0, weight=1)
        self._tags_content.grid_rowconfigure(1, weight=1)
        self._tags_content.grid_rowconfigure(4, weight=1)

        ctk.CTkLabel(self._tags_content, text="Current image",
                     font=ctk.CTkFont(size=11), text_color="gray60").grid(
            row=0, column=0, sticky="w", pady=(0, 2)
        )
        self._current_tag_frame = ctk.CTkScrollableFrame(self._tags_content, height=100)
        self._current_tag_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 4))

        sep_tags = ctk.CTkFrame(self._tags_content, height=1, fg_color="gray40")
        sep_tags.grid(row=2, column=0, sticky="ew", pady=2)

        master_hdr = ctk.CTkFrame(self._tags_content, fg_color="transparent")
        master_hdr.grid(row=3, column=0, sticky="ew", pady=(2, 2))
        master_hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            master_hdr, text="Session tag pool",
            font=ctk.CTkFont(size=11), text_color="gray60",
        ).grid(row=0, column=0, sticky="w")
        _mt_key = _normalize_master_tag_list_mode_key(
            get_profiles_manager().get_current_profile().get("master_tag_list_mode")
        )
        self._master_tag_pool_use_full = _mt_key == MASTER_TAG_LIST_MODE_FULL_KEY
        _mt_initial = (
            MASTER_TAG_LIST_MODE_FULL_UI if self._master_tag_pool_use_full
            else MASTER_TAG_LIST_MODE_SCANNED_UI
        )
        self._master_tag_list_mode_var = tk.StringVar(value=_mt_initial)
        _mt_menu = ctk.CTkOptionMenu(
            master_hdr,
            variable=self._master_tag_list_mode_var,
            values=[MASTER_TAG_LIST_MODE_SCANNED_UI, MASTER_TAG_LIST_MODE_FULL_UI],
            width=200,
            command=self._on_master_tag_list_mode_changed,
        )
        _mt_menu.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self._master_tag_list_menu = _mt_menu
        add_tooltip(
            _mt_menu,
            "Scanned: union of WD14 results only (manual tags stay on images but do not fill this list). "
            "All session: union of every tag on every image, including manual adds.",
        )

        self._master_tag_frame = ctk.CTkScrollableFrame(self._tags_content, height=100)
        self._master_tag_frame.grid(row=4, column=0, sticky="nsew")

        # ---- Caption panel (collapsible; prompts live here) ----
        self._caption_panel = ctk.CTkFrame(right, fg_color="transparent")
        self._caption_panel.pack(side="left", fill="both", expand=True, padx=(8, 0))

        caption_action_row = ctk.CTkFrame(self._caption_panel, fg_color="transparent")
        caption_action_row.pack(fill="x", pady=(0, 4))
        self._btn_caption = ctk.CTkButton(
            caption_action_row, text="Generate caption", width=120, command=self._gen_caption
        )
        self._btn_caption.pack(side="left", padx=(0, 6))
        add_tooltip(self._btn_caption, "Run the vision model to generate a natural-language caption for this image")
        self._btn_batch_caption = ctk.CTkButton(
            caption_action_row, text="Batch caption (all)", width=140, command=self._batch_gen_captions
        )
        self._btn_batch_caption.pack(side="left", padx=(0, 4))
        add_tooltip(self._btn_batch_caption, "Caption every image in the session using the vision model")

        caption_hdr = ctk.CTkFrame(self._caption_panel, fg_color="transparent")
        caption_hdr.pack(fill="x", pady=(0, 3))
        self._caption_toggle_btn = ctk.CTkButton(
            caption_hdr, text="◀", width=28, command=self._toggle_caption_panel
        )
        self._caption_toggle_btn.pack(side="left", padx=(0, 4))
        add_tooltip(self._caption_toggle_btn, "Collapse or expand the caption column")
        ctk.CTkLabel(caption_hdr, text="Caption",
                     font=ctk.CTkFont(weight="bold")).pack(side="left")

        self._caption_content = ctk.CTkFrame(self._caption_panel, fg_color="transparent")
        self._caption_content.pack(fill="both", expand=True)

        self.caption_text = ctk.CTkTextbox(self._caption_content)
        self.caption_text.pack(fill="both", expand=True, pady=(0, 4))

        self.prompt_entry = ctk.CTkEntry(
            self._caption_content, placeholder_text="e.g. Focus on the clothing style."
        )
        self.system_prompt_text = ctk.CTkTextbox(self._caption_content, height=80, wrap="word")

        preset_host = ctk.CTkFrame(self._caption_content, fg_color="transparent")

        def _preset_set_system(s: str) -> None:
            self.system_prompt_text.delete("1.0", "end")
            self.system_prompt_text.insert("1.0", s)

        def _preset_set_user(s: str) -> None:
            self.prompt_entry.delete(0, "end")
            if s:
                self.prompt_entry.insert(0, s)

        self._refresh_caption_preset_menu, self._caption_preset_var = build_preset_row(
            preset_host,
            set_system_text=_preset_set_system,
            set_user_text=_preset_set_user,
            save_system_to_profile=self._save_system_prompt_to_profile,
            get_system_text=lambda: self.system_prompt_text.get("1.0", "end-1c"),
            get_user_text=lambda: self.prompt_entry.get(),
        )
        preset_host.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(self._caption_content, text="User prompt (optional):",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(2, 0))
        self.prompt_entry.pack(fill="x", pady=(2, 0))
        add_tooltip(self.prompt_entry,
                    "Optional instruction appended to the request sent to the caption model.\n"
                    "Leave blank to use the model's default behaviour.\n"
                    "Caption presets can store a user line with each saved preset (Apply loads it here).")

        ctk.CTkLabel(self._caption_content, text="System prompt:",
                     font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(6, 0))
        self.system_prompt_text.pack(fill="x", pady=(2, 0))
        add_tooltip(self.system_prompt_text,
                    "System-level instruction sent to the caption model before the user prompt.\n"
                    "Changes here are saved to the current profile automatically.\n"
                    "Applies to all backends (local, Ollama, OpenAI, Anthropic, Gemini).\n"
                    "Use Caption presets above for built-in styles or your saved library.")
        # Persist to profile whenever the user stops editing
        self.system_prompt_text.bind(
            "<FocusOut>", lambda _e: self._save_system_prompt_to_profile()
        )

        # Populate system prompt from profile / config default
        self._load_system_prompt_from_profile()

        # Initial list build
        self._refresh_list()

    # ---- Tag picker helpers ----

    def _reset_tag_scroll_positions(self):
        """Scroll both tag lists to the top after a rebuild."""
        for sf in (getattr(self, "_current_tag_frame", None),
                   getattr(self, "_master_tag_frame", None)):
            if sf is not None and hasattr(sf, "_parent_canvas"):
                try:
                    sf._parent_canvas.yview_moveto(0)
                except Exception:
                    pass

    def _rebuild_tag_list(self, item=None):
        """Rebuild current-image and master tag lists for the given (or current) item."""
        if not hasattr(self, "_current_tag_frame") or not hasattr(self, "_master_tag_frame"):
            return
        self._build_tag_master_set()
        if item is None and self.current_index is not None:
            item = self.session.get_item(self.current_index)
        if item is None and self._selected_index_caption is not None:
            sel = self._selected_index_caption
            if 0 <= sel < len(self.session.items):
                item = self.session.get_item(sel)
                self.current_index = sel
        for w in self._current_tag_frame.winfo_children():
            w.destroy()
        for w in self._master_tag_frame.winfo_children():
            w.destroy()
        if item is None:
            if hasattr(self, "_tag_count_label"):
                self._tag_count_label.configure(text="")
            self.update_idletasks()
            self._reset_tag_scroll_positions()
            return
        filt = self._tag_filter_var.get().lower().strip() if hasattr(self, "_tag_filter_var") else ""
        active_set = set(item.tags)
        # Current image — tags on this image only (− to remove)
        for tag in list(item.tags):
            if filt and filt not in tag.lower():
                continue
            self._make_tag_row(self._current_tag_frame, tag, active=True, item=item)
        # Master list — show union of session tags (filter optional); cap rows for performance
        matches = [
            t for t in sorted(self._tag_master_set)
            if not filt or filt in t.lower()
        ]
        truncated = len(matches) > MASTER_TAG_MAX_RENDER
        show = matches[:MASTER_TAG_MAX_RENDER] if truncated else matches
        for tag in show:
            self._make_tag_row(
                self._master_tag_frame, tag, active=(tag in active_set), item=item
            )
        if truncated:
            ctk.CTkLabel(
                self._master_tag_frame,
                text=f"… {len(matches) - MASTER_TAG_MAX_RENDER} more — refine Filter",
                text_color="gray60",
                font=ctk.CTkFont(size=11),
            ).pack(anchor="w", padx=4, pady=(4, 2))
        if hasattr(self, "_tag_count_label"):
            self._tag_count_label.configure(text=f"({len(item.tags)})")
        self.update_idletasks()
        self._reset_tag_scroll_positions()

    def _make_tag_row(self, frame, tag: str, active: bool, item):
        """One compact row: tag text then +/- (no extra frames/lines — avoids scroll-canvas glitches)."""
        row = ctk.CTkFrame(frame, fg_color=("gray88", "gray25"), corner_radius=2)
        row.pack(fill="x", pady=1, padx=1)

        def toggle(t=tag, a=active):
            if a:
                if t in item.tags:
                    item.tags.remove(t)
                if t in item.tags_from_scan:
                    item.tags_from_scan.remove(t)
            else:
                if t not in item.tags:
                    item.tags.append(t)
            self._rebuild_tag_list(item)
            if self.on_changed:
                self.on_changed()

        ctk.CTkLabel(
            row, text=tag, anchor="w",
            text_color=("gray10", "gray90"),
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=(6, 4), pady=2)
        ctk.CTkButton(
            row,
            text="-" if active else "+",
            width=28, height=22,
            fg_color="darkred" if active else "#1f538d",
            command=toggle,
        ).pack(side="left", padx=(0, 4), pady=2)

    def _update_panel_pack_weights(self):
        """Give horizontal space to expanded panels only."""
        t_open = self._tags_panel_open
        c_open = self._caption_panel_open
        if t_open and c_open:
            self._tags_panel.pack_configure(fill="both", expand=True)
            self._caption_panel.pack_configure(fill="both", expand=True)
        elif t_open and not c_open:
            self._tags_panel.pack_configure(fill="both", expand=True)
            self._caption_panel.pack_configure(fill="y", expand=False)
        elif not t_open and c_open:
            self._tags_panel.pack_configure(fill="y", expand=False)
            self._caption_panel.pack_configure(fill="both", expand=True)
        else:
            self._tags_panel.pack_configure(fill="y", expand=False)
            self._caption_panel.pack_configure(fill="y", expand=False)

    def _toggle_tags_panel(self):
        self._tags_panel_open = not self._tags_panel_open
        if self._tags_panel_open:
            self._tags_content.pack(fill="both", expand=True)
            self._tags_toggle_btn.configure(text="◀")
        else:
            self._tags_content.pack_forget()
            self._tags_toggle_btn.configure(text="▶")
        self._update_panel_pack_weights()

    def _toggle_caption_panel(self):
        self._caption_panel_open = not self._caption_panel_open
        if self._caption_panel_open:
            self._caption_content.pack(fill="both", expand=True)
            self._caption_toggle_btn.configure(text="◀")
        else:
            self._caption_content.pack_forget()
            self._caption_toggle_btn.configure(text="▶")
        self._update_panel_pack_weights()

    def _add_manual_tag(self):
        """Add a manually typed tag to the current image (not treated as WD14 scan)."""
        tag = self._new_tag_entry.get().strip()
        if not tag or self.current_index is None:
            return
        item = self.session.get_item(self.current_index)
        if item and tag not in item.tags:
            item.tags.append(tag)
        self._new_tag_entry.delete(0, "end")
        self._rebuild_tag_list(item)

    def _build_tag_master_set(self):
        """Rebuild master tag pool from session items (scanned-only vs full union)."""
        self._tag_master_set = set()
        use_full = getattr(self, "_master_tag_pool_use_full", False)
        for it in self.session.items:
            self._tag_master_set.update(it.tags if use_full else it.tags_from_scan)

    # ---- Export ----

    def _export_markdown(self):
        """Export all session tags and captions to a numbered Markdown file."""
        from tkinter.filedialog import asksaveasfilename
        if not self.session.items:
            messagebox.showinfo("Export", "No images in session.")
            return
        path = asksaveasfilename(
            title="Export tags and captions",
            defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("All files", "*.*")],
        )
        if not path:
            return
        lines = ["# Tags & Captions Export\n\n"]
        for i, item in enumerate(self.session.items, 1):
            name = item.original_path.name
            tags = ", ".join(item.tags) if item.tags else "_(none)_"
            caption = item.caption.strip() if item.caption else "_(none)_"
            lines.append(f"## {i}. {name}\n\n")
            lines.append(f"**Tags:** {tags}\n\n")
            lines.append(f"**Caption:** {caption}\n\n")
            lines.append("---\n\n")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            messagebox.showinfo("Export", f"Exported {len(self.session.items)} entries to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export error", str(e))

    # ---- System prompt helpers ----

    def _load_system_prompt_from_profile(self):
        """Populate the system prompt textbox from the active profile (or config default)."""
        try:
            from core.data.profiles import get_profiles_manager
            from core import config as core_config
            pm = get_profiles_manager()
            value = pm.get_caption_system_prompt() or core_config.CAPTION_SYSTEM_PROMPT
        except Exception:
            from core import config as core_config
            value = core_config.CAPTION_SYSTEM_PROMPT
        self.system_prompt_text.delete("1.0", "end")
        if value:
            self.system_prompt_text.insert("1.0", value)
        refresh = getattr(self, "_refresh_caption_preset_menu", None)
        if callable(refresh):
            refresh()

    def _save_system_prompt_to_profile(self):
        """Write the current textbox value back to the active profile."""
        try:
            from core.data.profiles import get_profiles_manager
            pm = get_profiles_manager()
            value = self.system_prompt_text.get("1.0", "end-1c").strip()
            pm.set_caption_system_prompt(value)
        except Exception:
            pass

    def _load_index(self):
        try:
            idx = int(self.index_var.get().strip()) - 1
        except ValueError:
            idx = 0
        if idx < 0 or idx >= len(self.session.items):
            messagebox.showwarning("Load", "Invalid index.")
            return
        self.current_index = idx
        self._selected_index_caption = idx
        self._load_current_from_session()
        self.session.set_output_format(self.output_format_var.get())

    def _save_current(self):
        if self.current_index is None:
            return
        item = self.session.get_item(self.current_index)
        if not item:
            return
        # Tags are maintained directly in item.tags via the tag picker clicks
        item.caption = self.caption_text.get("1.0", "end-1c").strip()
        self.session.set_output_format(self.output_format_var.get())
        if self.on_changed:
            self.on_changed()

    def _save_and_confirm(self):
        """Save current edits and give brief visual feedback on the button."""
        self._save_current()
        self._refresh_list()
        self._btn_save_edits.configure(text="Saved!", fg_color="green")
        self.after(1200, lambda: self._btn_save_edits.configure(text="Save edits", fg_color="darkgreen"))

    def _set_loading(self, msg: str, busy: bool):
        self._loading_label.configure(text=msg)
        self._btn_tags.configure(state="disabled" if busy else "normal")
        self._btn_caption.configure(state="disabled" if busy else "normal")
        self._btn_batch_tags.configure(state="disabled" if busy else "normal")
        self._btn_batch_caption.configure(state="disabled" if busy else "normal")
        self._btn_save_edits.configure(state="disabled" if busy else "normal")
        if busy:
            self._btn_stop_caption.pack(
                in_=self._toolbar_general, side="left", padx=(0, 5),
                after=self._btn_save_edits,
            )
        else:
            self._btn_stop_caption.pack_forget()

    def _poll_batch_ui_queue(self):
        """Apply latest loading message from worker (main thread only)."""
        if not self._batch_ui_polling:
            return
        last_msg = None
        try:
            while True:
                try:
                    msg = self._batch_ui_queue.get_nowait()
                except queue.Empty:
                    break
                if isinstance(msg, tuple) and len(msg) >= 2 and msg[0] == "loading":
                    last_msg = msg[1]
        except Exception:
            pass
        if last_msg is not None:
            self._set_loading(last_msg, True)
        if self._batch_ui_polling:
            self.after(50, self._poll_batch_ui_queue)

    def _stop_captioning_batch(self):
        """Signal the running batch caption or tag loop to stop after the current image."""
        self._caption_stop_event.set()
        self._tags_stop_event.set()
        self._btn_stop_caption.configure(state="disabled", text="Stopping…")

    # ---- List + preview helpers ----

    def _refresh_list(self):
        """Rebuild the session image list and update preview."""
        frame = getattr(self, "_listbox_frame_captions", None)
        if frame is None:
            return
        for w in frame.winfo_children():
            w.destroy()
        items = self.session.items
        if not items:
            empty = ctk.CTkLabel(frame, text="No images in session.", text_color="gray60")
            empty.pack(anchor="w", pady=5)
            self._update_preview()
            return
        if self._selected_index_caption is None or not (0 <= self._selected_index_caption < len(items)):
            self._selected_index_caption = 0
        for i, item in enumerate(items):
            tags_flag = "T" if item.tags else "-"
            cap_flag = "C" if item.caption else "-"
            flags = f"[{tags_flag}{cap_flag}]"
            line = f"  {i+1}. {item.original_path.name} {flags}"
            is_selected = i == self._selected_index_caption
            row = ctk.CTkFrame(
                frame,
                fg_color=("gray75", "gray30") if is_selected else "transparent",
                corner_radius=4,
                cursor="hand2"
            )
            row.pack(fill="x", pady=2)
            lbl = ctk.CTkLabel(row, text=line, anchor="w")
            lbl.pack(fill="x", padx=8, pady=4)
            lbl.bind("<Button-1>", lambda e, idx=i: self._on_row_click(idx))
            row.bind("<Button-1>", lambda e, idx=i: self._on_row_click(idx))
        self._update_preview()
        self._rebuild_tag_list()

    def _on_row_click(self, index: int):
        """Handle click on a list row — save current edits before switching."""
        if index < 0 or index >= len(self.session.items):
            return
        self._save_current()
        self._selected_index_caption = index
        self.current_index = index
        self.index_var.set(str(index + 1))
        self._load_current_from_session()
        self._refresh_list()

    def _load_current_from_session(self):
        """Load tags/caption for current_index into editors and update preview."""
        if self.current_index is None or self.current_index < 0 or self.current_index >= len(self.session.items):
            return
        item = self.session.get_item(self.current_index)
        if not item:
            return
        self._rebuild_tag_list(item)
        self.caption_text.delete("1.0", "end")
        self.caption_text.insert("1.0", item.caption)
        self._update_preview()

    def _get_selected_list_index(self) -> Optional[int]:
        return self._selected_index_caption

    def _update_preview(self):
        """Load selected image into the zoom/pan canvas."""
        idx = self._get_selected_list_index()
        if idx is None or idx < 0 or idx >= len(self.session.items):
            self._preview_canvas.clear_image("Select an image to preview.")
            return
        item = self.session.get_item(idx)
        if not item or not item.original_path.exists():
            self._preview_canvas.clear_image("Image not found.")
            return
        try:
            image = Image.open(item.original_path).convert("RGB")
            self._preview_canvas.load_image(image)
        except Exception:
            self._preview_canvas.clear_image("Could not load image.")

    def _open_preview_window(self):
        """Open a resizable pop-out with zoom/pan for the selected image."""
        idx = self._get_selected_list_index()
        if idx is None or idx < 0 or idx >= len(self.session.items):
            messagebox.showinfo("Preview", "Select an image first.")
            return
        item = self.session.get_item(idx)
        if not item or not item.original_path.exists():
            messagebox.showwarning("Preview", "Image file not found.")
            return
        try:
            image = Image.open(item.original_path).convert("RGB")
        except Exception as e:
            messagebox.showerror("Preview", str(e))
            return
        win = ctk.CTkToplevel(self.winfo_toplevel())
        win.title(f"Preview — #{idx + 1} {item.original_path.name}")
        win.transient(self.winfo_toplevel())
        cw = min(image.width, 900)
        ch = min(image.height, 700)
        win.geometry(f"{cw}x{ch + 60}")
        win.resizable(True, True)
        f = ctk.CTkFrame(win, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        canvas = _make_zoom_pan_canvas(f, width=cw, height=ch)
        canvas.pack(fill="both", expand=True)
        canvas.load_image(image)
        info = ctk.CTkLabel(win, text=f"#{idx + 1} — {item.original_path.name}  |  {image.width}×{image.height}px",
                            text_color="gray70")
        info.pack(pady=(4, 0))
        bot = ctk.CTkFrame(win, fg_color="transparent")
        bot.pack(pady=(4, 8))
        ctk.CTkButton(bot, text="Reset zoom", width=90,
                      command=lambda: canvas.load_image(image)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(bot, text="Close", width=80, command=win.destroy).pack(side="left")

    def _gen_tags(self):
        if self.current_index is None:
            messagebox.showinfo("Generate tags", "Load an image first (set index and click Load).")
            return
        item = self.session.get_item(self.current_index)
        if not item or not item.original_path.exists():
            return
        get_vram_manager().ensure_state(State.CAPTIONING)
        if get_tagger().load_model() is None:
            messagebox.showwarning("WD14", "WD14 failed to load. Check log.")
            return
        self._set_loading("Generating tags…", True)
        path, th = item.original_path, self.threshold_var.get()

        def work():
            return tag_image(path, threshold=th)

        def on_done(tags):
            self._set_loading("", False)
            if tags is None:
                return
            item.tags = tags
            item.tags_from_scan = list(tags)
            self._rebuild_tag_list(item)
            if self.on_changed:
                self.on_changed()

        def run():
            try:
                result = work()
                _schedule_main(lambda: on_done(result))
            except Exception as e:
                err = str(e)

                def _err():
                    self._set_loading("", False)
                    messagebox.showerror("Tags", err)

                _schedule_main(_err)

        threading.Thread(target=run, daemon=True).start()

    def _gen_caption(self):
        if self.current_index is None:
            messagebox.showinfo("Generate caption", "Load an image first.")
            return
        item = self.session.get_item(self.current_index)
        if not item or not item.original_path.exists():
            return
        core_config.CAPTION_TRIGGER_WORDS = (self.trigger_entry.get() or "").strip()
        prompt = self.prompt_entry.get()
        sys_prompt = self.system_prompt_text.get("1.0", "end-1c").strip() if hasattr(self, "system_prompt_text") else ""
        self._save_system_prompt_to_profile()
        self._set_loading("Generating caption…", True)
        path, tags_snapshot = item.original_path, list(item.tags)

        def work():
            return generate_caption(path, tags_snapshot, prompt,
                                    system_prompt_override=sys_prompt or None)

        def on_done(caption):
            self._set_loading("", False)
            if caption is None:
                return
            item.caption = caption
            self.caption_text.delete("1.0", "end")
            self.caption_text.insert("1.0", caption)
            if self.on_changed:
                self.on_changed()

        def run():
            try:
                result = work()
                _schedule_main(lambda: on_done(result))
            except Exception as e:
                err = str(e)

                def _err():
                    self._set_loading("", False)
                    messagebox.showerror("Caption", err)

                _schedule_main(_err)

        threading.Thread(target=run, daemon=True).start()

    def _batch_gen_tags(self):
        """Generate tags for all session items."""
        if not self.session.items:
            messagebox.showinfo("Batch tags", "No images in session.")
            return
        get_vram_manager().ensure_state(State.CAPTIONING)
        if get_tagger().load_model() is None:
            messagebox.showwarning("WD14", "WD14 failed to load. Check log.")
            return
        th = self.threshold_var.get()
        # Reset stop state so a previous Stop press doesn't immediately abort
        self._tags_stop_event.clear()
        self._btn_stop_caption.configure(state="normal", text="Stop")
        items_snapshot = list(self.session.items)
        total = len(items_snapshot)
        self._batch_ui_polling = True
        self._set_loading("Batch tagging…", True)
        self.after(50, self._poll_batch_ui_queue)

        def work():
            from ui.app_main import set_progress, set_status
            tagged = skipped = 0
            for i, item in enumerate(items_snapshot, 1):
                if self._tags_stop_event.is_set():
                    break
                if not item.original_path.exists():
                    skipped += 1
                    continue
                self._batch_ui_queue.put(("loading", f"Tagging {i}/{total}…"))
                set_progress(i, total, f"Tagging {i}/{total}: {item.original_path.name}")
                result = tag_image(item.original_path, threshold=th)
                if result:
                    item.tags = result
                    item.tags_from_scan = list(result)
                    tagged += 1
                else:
                    skipped += 1
            set_status("Ready")
            return tagged, skipped, self._tags_stop_event.is_set()

        def on_done(tagged, skipped, stopped):
            self._batch_ui_polling = False
            try:
                while True:
                    self._batch_ui_queue.get_nowait()
            except queue.Empty:
                pass
            self._set_loading("", False)
            if self.on_changed:
                self.on_changed()
            self._refresh_list()
            msg = f"Tagged {tagged} image(s)."
            if skipped:
                msg += f"\n{skipped} image(s) skipped (file not found or no tags returned)."
            if stopped:
                msg += "\n(Stopped early by user.)"
            messagebox.showinfo("Batch tags", msg)

        def run():
            try:
                result = work()
                _schedule_main(lambda r=result: on_done(*r))
            except Exception as e:
                err = str(e)

                def _err():
                    self._batch_ui_polling = False
                    try:
                        while True:
                            self._batch_ui_queue.get_nowait()
                    except queue.Empty:
                        pass
                    self._set_loading("", False)
                    messagebox.showerror("Batch tags", err)

                _schedule_main(_err)

        threading.Thread(target=run, daemon=True).start()

    def _show_caption_failure_modal(self, n_failed: int, total: int):
        """Show an actionable modal when batch captions fail, with an Open Settings button."""
        modal = ctk.CTkToplevel(self.winfo_toplevel())
        modal.title("Caption Failures")
        modal.resizable(False, False)
        modal.grab_set()
        ctk.CTkLabel(
            modal,
            text=f"{n_failed} of {total} caption(s) failed.",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(padx=24, pady=(20, 6))
        ctk.CTkLabel(
            modal,
            text=(
                "The selected caption backend may be unavailable or misconfigured.\n"
                "Open Settings → Caption Model / Backend to choose a different model\n"
                "or switch to a local model."
            ),
            wraplength=380,
            justify="left",
        ).pack(padx=24, pady=(0, 18))
        btn_row = ctk.CTkFrame(modal, fg_color="transparent")
        btn_row.pack(pady=(0, 18))

        def _open_settings():
            modal.destroy()
            if self._open_settings_cb:
                self._open_settings_cb()

        ctk.CTkButton(btn_row, text="Open Settings", width=130,
                      command=_open_settings).pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text="Dismiss", width=90,
                      command=modal.destroy).pack(side="left", padx=8)

    def _batch_gen_captions(self):
        """Generate captions for all session items (ensuring tags exist)."""
        if not self.session.items:
            messagebox.showinfo("Batch caption", "No images in session.")
            return
        core_config.CAPTION_TRIGGER_WORDS = (self.trigger_entry.get() or "").strip()
        prompt = self.prompt_entry.get()
        sys_prompt = self.system_prompt_text.get("1.0", "end-1c").strip() if hasattr(self, "system_prompt_text") else ""
        self._save_system_prompt_to_profile()
        items_snapshot = list(self.session.items)
        self._caption_stop_event.clear()
        self._tags_stop_event.clear()
        self._btn_stop_caption.configure(state="normal", text="Stop")
        self._batch_ui_polling = True
        self._set_loading("Batch captioning…", True)
        self.after(50, self._poll_batch_ui_queue)

        total = len(items_snapshot)

        def work():
            from ui.app_main import set_progress, set_status
            th = self.threshold_var.get()
            failed = 0
            done = 0
            for i, item in enumerate(items_snapshot, 1):
                if self._caption_stop_event.is_set():
                    break
                if not item.original_path.exists():
                    continue
                set_progress(i, total, f"Captioning {i}/{total}: {item.original_path.name}")
                if not item.tags:
                    scanned = tag_image(item.original_path, threshold=th)
                    item.tags = list(scanned)
                    item.tags_from_scan = list(scanned)
                caption = generate_caption(item.original_path, list(item.tags), prompt,
                                           system_prompt_override=sys_prompt or None)
                if not caption:
                    failed += 1
                else:
                    item.caption = caption
                done += 1
                fail_hint = (
                    f" ({failed} failed — check Settings → Caption source)"
                    if failed else ""
                )
                self._batch_ui_queue.put(("loading", f"Captioning {i}/{total}…{fail_hint}"))
            set_status("Ready")
            return done, failed, self._caption_stop_event.is_set()

        def on_done(done, failed, stopped):
            self._batch_ui_polling = False
            try:
                while True:
                    self._batch_ui_queue.get_nowait()
            except queue.Empty:
                pass
            self._set_loading("", False)
            idx = self.current_index
            if idx is None and self._selected_index_caption is not None:
                sel = self._selected_index_caption
                if 0 <= sel < len(self.session.items):
                    idx = sel
                    self.current_index = sel
            if idx is not None:
                cap_item = self.session.get_item(idx)
                if cap_item:
                    self.caption_text.delete("1.0", "end")
                    self.caption_text.insert("1.0", cap_item.caption)
            if self.on_changed:
                self.on_changed()
            self._refresh_list()
            summary = f"{'Stopped early. ' if stopped else ''}Captioned {done} image(s)."
            if failed:
                self._show_caption_failure_modal(failed, len(items_snapshot))
            else:
                messagebox.showinfo("Batch caption", summary)

        def run():
            try:
                result = work()
                _schedule_main(lambda r=result: on_done(*r))
            except Exception as e:
                err = str(e)

                def _err():
                    self._batch_ui_polling = False
                    try:
                        while True:
                            self._batch_ui_queue.get_nowait()
                    except queue.Empty:
                        pass
                    self._set_loading("", False)
                    messagebox.showerror("Batch caption", err)

                _schedule_main(_err)

        threading.Thread(target=run, daemon=True).start()

    def on_leave(self):
        self._save_current()

    def on_drop(self, paths: List[Path]) -> bool:
        return False


class StepFinalize(ctk.CTkFrame):
    """Step 4: Summary and Finalize button."""
    def __init__(self, parent, on_finalize_done: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.on_finalize_done = on_finalize_done
        self.session = get_session()
        self._summary_label = None
        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(self, text="Review and finalize. This will write output images and sidecar .txt files, then archive originals to processed.",
                     font=ctk.CTkFont(size=12)).pack(anchor="w", padx=10, pady=(10, 5))
        options = ctk.CTkFrame(self, fg_color="transparent")
        options.pack(fill="x", padx=10, pady=(0, 5))
        self.move_originals_var = ctk.BooleanVar(value=True)
        _move_check = ctk.CTkCheckBox(
            options,
            text="Move originals to processed (disable to copy instead)",
            variable=self.move_originals_var
        )
        _move_check.pack(side="left", padx=(0, 12))
        add_tooltip(_move_check, "Move source images to the processed/ subfolder after export; uncheck to copy instead")
        ctk.CTkLabel(options, text="Finalize workers:").pack(side="left", padx=(0, 5))
        self.finalize_workers_var = ctk.StringVar(value="1")
        _workers_om = ctk.CTkOptionMenu(
            options,
            variable=self.finalize_workers_var,
            values=["1", "2", "4"],
            width=70
        )
        _workers_om.pack(side="left")
        add_tooltip(_workers_om, "Number of parallel threads used when writing output files — more workers = faster on SSDs")
        self._summary_label = ctk.CTkLabel(self, text="", anchor="w", justify="left")
        self._summary_label.pack(fill="x", padx=10, pady=10)
        self._finalize_btn = ctk.CTkButton(self, text="Finalize", command=self._finalize, width=140, height=40,
                                           font=ctk.CTkFont(size=14, weight="bold"))
        self._finalize_btn.pack(pady=20)
        add_tooltip(self._finalize_btn, "Write all output images and .txt sidecars, then archive originals")

    def refresh_summary(self):
        n = len(self.session.items)
        out = str(self.session.output_folder) if self.session.output_folder else "(not set)"
        proc = str(self.session.get_processed_dir()) if self.session.get_processed_dir() else "(not set)"
        self._summary_label.configure(
            text=f"Images: {n}\nOutput: {out}\nProcessed folder: {proc}"
        )

    def _finalize(self):
        if not self.session.output_folder:
            messagebox.showerror("Finalize", "Output folder not set. Go back to Step 1.")
            return
        if not self.session.items:
            messagebox.showinfo("Finalize", "No images in session.")
            return
        proc = self.session.get_processed_dir()
        if not proc:
            messagebox.showerror("Finalize", "Processed folder could not be resolved.")
            return
        archive_mode = "move" if self.move_originals_var.get() else "copy"
        workers = int(self.finalize_workers_var.get())
        self.session.set_finalize_behavior(move_originals=self.move_originals_var.get(), workers=workers)
        if not messagebox.askyesno("Finalize", f"Finalize {len(self.session.items)} image(s)?\n\nArchive mode: {archive_mode}\nWorkers: {workers}\nOutput: {self.session.output_folder}\nProcessed: {proc}"):
            return
        self._finalize_btn.configure(state="disabled")

        def work():
            from ui.app_main import set_status
            set_status(f"Finalizing {len(self.session.items)} image(s)…", busy=True)
            return self.session.finalize()

        def on_done(result):
            from ui.app_main import set_status
            success, errors = result
            self._finalize_btn.configure(state="normal")
            set_status("Ready")
            msg = f"Done. {success} image(s) finalized."
            if errors:
                msg += "\n\nErrors:\n" + "\n".join(errors[:10])
                if len(errors) > 10:
                    msg += f"\n... and {len(errors) - 10} more."
            messagebox.showinfo("Finalize", msg)
            if self.on_finalize_done:
                self.on_finalize_done()

        def run():
            try:
                result = work()
                self.after(0, lambda: on_done(result))
            except Exception as e:
                self.after(0, lambda: self._finalize_btn.configure(state="normal"))
                self.after(0, lambda: messagebox.showerror("Finalize", str(e)))
                from ui.app_main import set_status
                set_status("Ready")

        threading.Thread(target=run, daemon=True).start()
