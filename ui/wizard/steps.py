"""Wizard step frames: Directories, Images, Tags/Captions, Finalize."""

import customtkinter as ctk
import tkinter as tk
from pathlib import Path
from typing import Optional, Callable, List
from tkinter import filedialog, messagebox
import threading

from PIL import Image, ImageTk
from core.session import get_session, SessionItem
from core.config import VALID_EXTENSIONS
from core.data.profiles import get_profiles_manager
from core.data.file_handler import load_image_files
from core.ai.vram import get_vram_manager, State
from core.ai.tagger import tag_image, get_tagger
from core.ai.captioner import generate_caption
import core.config as core_config
from ui.tooltip import add_tooltip


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
        _rename_btn = ctk.CTkButton(btn_frame, text="Rename…", width=100, command=self._rename_selected)
        _rename_btn.pack(side="left", padx=5)
        add_tooltip(_rename_btn, "Rename the selected image's output filename stem")
        ctk.CTkLabel(btn_frame, text="Batch:").pack(side="left", padx=(15, 2))
        self._prefix_entry = ctk.CTkEntry(btn_frame, width=80, placeholder_text="Prefix")
        self._prefix_entry.pack(side="left", padx=2)
        add_tooltip(self._prefix_entry, "Text to prepend to every image output name")
        _prefix_btn = ctk.CTkButton(btn_frame, text="Add prefix to all", width=110, command=self._batch_prefix)
        _prefix_btn.pack(side="left", padx=2)
        add_tooltip(_prefix_btn, "Prepend the prefix text to every image output name")
        self._suffix_entry = ctk.CTkEntry(btn_frame, width=80, placeholder_text="Suffix")
        self._suffix_entry.pack(side="left", padx=2)
        add_tooltip(self._suffix_entry, "Text to append to every image output name")
        _suffix_btn = ctk.CTkButton(btn_frame, text="Add suffix to all", width=110, command=self._batch_suffix)
        _suffix_btn.pack(side="left", padx=5)
        add_tooltip(_suffix_btn, "Append the suffix text to every image output name")
        ctk.CTkLabel(top_frame, text="Click an image below to select it; use Remove or Rename on the selection. Ctrl+click to select multiple.",
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
    def __init__(self, parent, on_changed: Optional[Callable[[], None]] = None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.on_changed = on_changed
        self.session = get_session()
        self.current_index: Optional[int] = None
        self._build_ui()

    def apply_profile(self, profile: dict) -> None:
        """Apply profile defaults (e.g. trigger words) to this step."""
        self.trigger_entry.delete(0, "end")
        self.trigger_entry.insert(0, profile.get("default_trigger_words") or "")
        fmt = profile.get("default_output_format", "Natural language")
        if fmt in ("Tags only", "Natural language", "Both"):
            self.output_format_var.set(fmt)
        self.session.set_output_format(self.output_format_var.get())

    def _build_ui(self):
        # Top controls
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(top, text="Select an image (index), then generate or edit tags and caption.", font=ctk.CTkFont(size=12)).pack(anchor="w")
        self.index_var = ctk.StringVar(value="1")
        ctk.CTkLabel(top, text="Image index:").pack(side="left", padx=(0, 5))
        _index_entry = ctk.CTkEntry(top, textvariable=self.index_var, width=60)
        _index_entry.pack(side="left", padx=(0, 10))
        add_tooltip(_index_entry, "1-based index of the image to load from the session list")
        _load_btn = ctk.CTkButton(top, text="Load", width=70, command=self._load_index)
        _load_btn.pack(side="left", padx=(0, 5))
        add_tooltip(_load_btn, "Load the image at the given index into the tag and caption editors")
        ctk.CTkLabel(top, text="Tag threshold:").pack(side="left", padx=(10, 2))
        self.threshold_var = ctk.DoubleVar(value=0.5)
        _threshold_slider = ctk.CTkSlider(top, from_=0.35, to=0.85, variable=self.threshold_var, width=80)
        _threshold_slider.pack(side="left", padx=2)
        add_tooltip(_threshold_slider, "Minimum confidence for a WD14 tag to be included (higher = fewer, more confident tags)")
        self._btn_tags = ctk.CTkButton(top, text="Generate tags", width=100, command=self._gen_tags)
        self._btn_tags.pack(side="left", padx=(10, 5))
        add_tooltip(self._btn_tags, "Run the WD14 tagger on this image")
        self._btn_caption = ctk.CTkButton(top, text="Generate caption", width=120, command=self._gen_caption)
        self._btn_caption.pack(side="left", padx=5)
        add_tooltip(self._btn_caption, "Run the vision model to generate a natural-language caption for this image")
        self._btn_batch_tags = ctk.CTkButton(top, text="Batch tags (all)", width=120, command=self._batch_gen_tags)
        self._btn_batch_tags.pack(side="left", padx=(10, 5))
        add_tooltip(self._btn_batch_tags, "Tag every image in the session using WD14")
        self._btn_batch_caption = ctk.CTkButton(top, text="Batch caption (all)", width=140, command=self._batch_gen_captions)
        self._btn_batch_caption.pack(side="left", padx=5)
        add_tooltip(self._btn_batch_caption, "Caption every image in the session using the vision model")
        self._btn_save_edits = ctk.CTkButton(top, text="Save edits", width=90, fg_color="darkgreen", command=self._save_and_confirm)
        self._btn_save_edits.pack(side="left", padx=(10, 5))
        add_tooltip(self._btn_save_edits, "Save the current tags and caption edits to the session (auto-saved when switching images)")
        self._loading_label = ctk.CTkLabel(top, text="", text_color="gray70")
        self._loading_label.pack(side="left", padx=(10, 0))
        ctk.CTkLabel(top, text="Output:").pack(side="left", padx=(10, 2))
        self.output_format_var = ctk.StringVar(value="Natural language")
        om = ctk.CTkOptionMenu(top, variable=self.output_format_var, values=["Tags only", "Natural language", "Both"], width=120)
        om.pack(side="left", padx=2)
        add_tooltip(om, "Choose whether to write tags only, a natural-language caption, or both to the .txt sidecar")
        self.output_format_var.trace_add("write", lambda *a: self.session.set_output_format(self.output_format_var.get()))
        ctk.CTkLabel(top, text="Trigger words:").pack(side="left", padx=(10, 2))
        self.trigger_entry = ctk.CTkEntry(top, placeholder_text="e.g. mylora", width=100)
        self.trigger_entry.pack(side="left", padx=2)
        add_tooltip(self.trigger_entry, "Words prepended to every caption (e.g. your LoRA trigger token)")

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

        # Right column: tags | caption side-by-side, prompt below
        right = ctk.CTkFrame(content, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        right.grid_columnconfigure(0, weight=1)
        right.grid_columnconfigure(1, weight=1)
        right.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(right, text="Tags", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 5)
        )
        self.tags_text = ctk.CTkTextbox(right)
        self.tags_text.grid(row=1, column=0, sticky="nsew")

        ctk.CTkLabel(right, text="Caption", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=1, sticky="w", pady=(0, 5), padx=(8, 0)
        )
        self.caption_text = ctk.CTkTextbox(right)
        self.caption_text.grid(row=1, column=1, sticky="nsew", padx=(8, 0))

        self.prompt_entry = ctk.CTkEntry(right, placeholder_text="Optional prompt for caption…")
        self.prompt_entry.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(5, 0))

        # Initial list build
        self._refresh_list()

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
        tags_str = self.tags_text.get("1.0", "end-1c").strip()
        item.tags = [t.strip() for t in tags_str.split(",") if t.strip()]
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
        self.tags_text.delete("1.0", "end")
        self.tags_text.insert("1.0", ", ".join(item.tags))
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
            self.tags_text.delete("1.0", "end")
            self.tags_text.insert("1.0", ", ".join(tags))
            if self.on_changed:
                self.on_changed()

        def run():
            try:
                result = work()
                self.after(0, lambda: on_done(result))
            except Exception as e:
                self.after(0, lambda: self._set_loading("", False))
                self.after(0, lambda: messagebox.showerror("Tags", str(e)))

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
        self._set_loading("Generating caption…", True)
        path, tags_snapshot = item.original_path, list(item.tags)

        def work():
            return generate_caption(path, tags_snapshot, prompt)

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
                self.after(0, lambda: on_done(result))
            except Exception as e:
                self.after(0, lambda: self._set_loading("", False))
                self.after(0, lambda: messagebox.showerror("Caption", str(e)))

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
        items_snapshot = list(self.session.items)
        self._set_loading("Batch tagging…", True)

        total = len(items_snapshot)

        def work():
            from ui.app_main import set_progress, set_status
            for i, item in enumerate(items_snapshot, 1):
                if item.original_path.exists():
                    self.after(0, lambda i=i: self._set_loading(f"Tagging {i}/{total}…", True))
                    set_progress(i, total, f"Tagging {i}/{total}: {item.original_path.name}")
                    item.tags = tag_image(item.original_path, threshold=th)
            set_status("Ready")

        def on_done():
            self._set_loading("", False)
            if self.current_index is not None:
                item = self.session.get_item(self.current_index)
                if item:
                    self.tags_text.delete("1.0", "end")
                    self.tags_text.insert("1.0", ", ".join(item.tags))
            if self.on_changed:
                self.on_changed()
            self._refresh_list()
            messagebox.showinfo("Batch tags", f"Tagged {len(items_snapshot)} image(s).")

        def run():
            try:
                work()
                self.after(0, on_done)
            except Exception as e:
                self.after(0, lambda: self._set_loading("", False))
                self.after(0, lambda: messagebox.showerror("Batch tags", str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _batch_gen_captions(self):
        """Generate captions for all session items (ensuring tags exist)."""
        if not self.session.items:
            messagebox.showinfo("Batch caption", "No images in session.")
            return
        core_config.CAPTION_TRIGGER_WORDS = (self.trigger_entry.get() or "").strip()
        prompt = self.prompt_entry.get()
        items_snapshot = list(self.session.items)
        self._set_loading("Batch captioning…", True)

        total = len(items_snapshot)

        def work():
            from ui.app_main import set_progress, set_status
            th = self.threshold_var.get()
            for i, item in enumerate(items_snapshot, 1):
                if not item.original_path.exists():
                    continue
                self.after(0, lambda i=i: self._set_loading(f"Captioning {i}/{total}…", True))
                set_progress(i, total, f"Captioning {i}/{total}: {item.original_path.name}")
                if not item.tags:
                    item.tags = tag_image(item.original_path, threshold=th)
                item.caption = generate_caption(item.original_path, list(item.tags), prompt)
            set_status("Ready")

        def on_done():
            self._set_loading("", False)
            if self.current_index is not None:
                item = self.session.get_item(self.current_index)
                if item:
                    self.tags_text.delete("1.0", "end")
                    self.tags_text.insert("1.0", ", ".join(item.tags))
                    self.caption_text.delete("1.0", "end")
                    self.caption_text.insert("1.0", item.caption)
            if self.on_changed:
                self.on_changed()
            self._refresh_list()
            messagebox.showinfo("Batch caption", f"Captioned {len(items_snapshot)} image(s).")

        def run():
            try:
                work()
                self.after(0, on_done)
            except Exception as e:
                self.after(0, lambda: self._set_loading("", False))
                self.after(0, lambda: messagebox.showerror("Batch caption", str(e)))

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
