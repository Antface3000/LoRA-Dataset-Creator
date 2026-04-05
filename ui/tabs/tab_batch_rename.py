"""Batch rename images using WD14 tagger: prepend top tags to filenames. Supports dry run."""

import re
import threading
import customtkinter as ctk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import List, Optional, Tuple

from core.config import VALID_EXTENSIONS
from core.ai.tagger import get_tagger, tag_image
from core.ai.vram import get_vram_manager, State
from ui.tooltip import add_tooltip


def _clean_tag(tag: str) -> str:
    """Replace spaces with underscores, remove parentheses and content inside."""
    s = re.sub(r"\([^)]*\)", "", tag).strip()
    s = s.replace(" ", "_").strip("_")
    return s if s else tag.replace(" ", "_")


def _clean_prepend_word(word: str) -> str:
    """Normalize a manual prepend word for use in filename (underscores, no parens)."""
    s = re.sub(r"\([^)]*\)", "", word).strip()
    s = s.replace(" ", "_").strip("_")
    return s if s else word.replace(" ", "_")


def _propose_name(
    image_path: Path,
    tags: List[str],
    max_tags: int,
    omit_words: Optional[List[str]] = None,
    prepend_words: Optional[List[str]] = None,
) -> str:
    """Build new filename: [prepend]_tag1_tag2_..._original_stem.ext (prepend first, then tags; omit_words excluded)."""
    prepend_cleaned = [_clean_prepend_word(w) for w in (prepend_words or []) if _clean_prepend_word(w)]
    omit_set = {w.strip().lower() for w in (omit_words or []) if w.strip()}
    chosen = []
    for t in tags:
        if not t:
            continue
        ct = _clean_tag(t)
        if ct and ct.lower() not in omit_set:
            chosen.append(ct)
            if len(chosen) >= max_tags:
                break
    prefix_parts = prepend_cleaned + chosen
    prefix = "_".join(prefix_parts)
    stem = image_path.stem
    ext = image_path.suffix
    if prefix:
        return f"{prefix}_{stem}{ext}"
    return image_path.name


class TabBatchRename(ctk.CTkFrame):
    """Tab content: folder selection, WD14 analyze, dry-run list, apply renames."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._folder: Optional[Path] = None
        self._proposals: List[Tuple[Path, str]] = []  # (original_path, proposed_name)
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # Folder
        row0 = ctk.CTkFrame(self, fg_color="transparent")
        row0.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        row0.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(row0, text="Folder:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._path_var = ctk.StringVar(value="(none)")
        ctk.CTkLabel(row0, textvariable=self._path_var, anchor="w").grid(row=0, column=1, sticky="ew")
        _browse_btn = ctk.CTkButton(row0, text="Browse…", width=100, command=self._browse)
        _browse_btn.grid(row=0, column=2, padx=(8, 0))
        add_tooltip(_browse_btn, "Select the folder of images to rename")

        # Options
        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 5))
        row1.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(row1, text="Confidence threshold:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self._threshold_var = ctk.DoubleVar(value=0.35)
        th_label = ctk.CTkLabel(row1, text="0.35")
        _th_slider = ctk.CTkSlider(
            row1, from_=0.2, to=0.6, variable=self._threshold_var, width=120,
            command=lambda v: th_label.configure(text=f"{float(v):.2f}")
        )
        _th_slider.grid(row=0, column=1, sticky="w", padx=4)
        add_tooltip(_th_slider, "Minimum WD14 tag confidence to include in the rename (higher = fewer, more confident tags)")
        th_label.grid(row=0, column=2, sticky="w", padx=(8, 0))
        ctk.CTkLabel(row1, text="Max tags to prepend (5–10):").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        self._max_tags_var = ctk.IntVar(value=7)
        mt_label = ctk.CTkLabel(row1, text="7")
        _mt_slider = ctk.CTkSlider(
            row1, from_=5, to=10, variable=self._max_tags_var, width=120,
            command=lambda v: mt_label.configure(text=str(int(float(v))))
        )
        _mt_slider.grid(row=1, column=1, sticky="w", padx=4, pady=(8, 0))
        add_tooltip(_mt_slider, "Maximum number of tags to prepend to the filename")
        mt_label.grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(8, 0))
        ctk.CTkLabel(row1, text="Words to omit:").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        self._omit_entry = ctk.CTkEntry(
            row1, width=280, placeholder_text="e.g. 1girl, solo, portrait (comma or space separated)"
        )
        self._omit_entry.grid(row=2, column=1, columnspan=2, sticky="ew", padx=4, pady=(8, 0))
        add_tooltip(self._omit_entry, "Tags to exclude from the renamed filename (comma or space separated)")
        ctk.CTkLabel(row1, text="Prepend (manual):").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        self._prepend_entry = ctk.CTkEntry(
            row1, width=280, placeholder_text="e.g. character_name, style (added before tags; comma or space separated)"
        )
        self._prepend_entry.grid(row=3, column=1, columnspan=2, sticky="ew", padx=4, pady=(8, 0))
        add_tooltip(self._prepend_entry, "Text always added at the start of every renamed filename, before AI tags")

        # Simple rename row
        ctk.CTkLabel(row1, text="Simple base name:").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=(8, 0))
        self._base_name_entry = ctk.CTkEntry(
            row1, width=160, placeholder_text="e.g. character_name"
        )
        self._base_name_entry.grid(row=4, column=1, sticky="w", padx=4, pady=(8, 0))
        add_tooltip(self._base_name_entry, "Fixed base name for all files (used with Preview simple rename)")
        simple_opts = ctk.CTkFrame(row1, fg_color="transparent")
        simple_opts.grid(row=4, column=2, sticky="w", padx=4, pady=(8, 0))
        self._seq_suffix_var = ctk.BooleanVar(value=True)
        _seq_check = ctk.CTkCheckBox(simple_opts, text="Sequential suffix", variable=self._seq_suffix_var, width=140)
        _seq_check.pack(side="left", padx=(0, 8))
        add_tooltip(_seq_check, "Append a sequential number (_001, _002, …) to each renamed file")
        ctk.CTkLabel(simple_opts, text="Start:").pack(side="left")
        self._seq_start_entry = ctk.CTkEntry(simple_opts, width=48, placeholder_text="1")
        self._seq_start_entry.insert(0, "1")
        self._seq_start_entry.pack(side="left", padx=(4, 8))
        add_tooltip(self._seq_start_entry, "Starting number for the sequential suffix (default 1)")
        ctk.CTkLabel(simple_opts, text="Pad:").pack(side="left")
        self._seq_pad_var = ctk.StringVar(value="3")
        _pad_menu = ctk.CTkOptionMenu(simple_opts, variable=self._seq_pad_var, values=["1", "2", "3", "4"], width=56)
        _pad_menu.pack(side="left", padx=4)
        add_tooltip(_pad_menu, "Number of digits in the suffix (3 = 001, 4 = 0001)")

        btn_frame = ctk.CTkFrame(row1, fg_color="transparent")
        btn_frame.grid(row=0, column=3, rowspan=5, padx=(15, 0))
        self._analyze_btn = ctk.CTkButton(btn_frame, text="Analyze (dry run)", width=140, command=self._analyze)
        self._analyze_btn.pack(pady=(0, 4))
        add_tooltip(self._analyze_btn, "Preview proposed renames using WD14 AI tags without changing any files")
        _prepend_preview_btn = ctk.CTkButton(btn_frame, text="Preview prepend only", width=140, command=self._build_manual_list)
        _prepend_preview_btn.pack(pady=(0, 4))
        add_tooltip(_prepend_preview_btn, "Show filenames with only the manual prepend text applied (no AI tagging)")
        _simple_btn = ctk.CTkButton(btn_frame, text="Preview simple rename", width=140, command=self._build_simple_rename_list)
        _simple_btn.pack(pady=0)
        add_tooltip(_simple_btn, "Preview renames using the base name and optional sequential suffix")

        # List
        list_frame = ctk.CTkScrollableFrame(self)
        list_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
        list_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(list_frame, text="Proposed renames: use Analyze (dry run) for AI tags, or Preview prepend only; then Apply to rename on disk.", font=ctk.CTkFont(size=11), text_color="gray70").grid(row=0, column=0, sticky="w", pady=(0, 5))
        self._list_text = ctk.CTkTextbox(list_frame, wrap="none", state="disabled")
        self._list_text.grid(row=1, column=0, sticky="nsew", pady=(0, 5))
        list_frame.grid_rowconfigure(1, weight=1)

        # Apply / Reset
        row3 = ctk.CTkFrame(self, fg_color="transparent")
        row3.grid(row=3, column=0, sticky="ew", padx=10, pady=(5, 10))
        _apply_btn = ctk.CTkButton(row3, text="Apply renames", width=120, command=self._apply, fg_color="darkgreen")
        _apply_btn.pack(side="left", padx=(0, 8))
        add_tooltip(_apply_btn, "Permanently rename all files on disk according to the proposed list")
        _reset_btn = ctk.CTkButton(row3, text="Reset list", width=100, command=self._reset_list)
        _reset_btn.pack(side="left", padx=(0, 8))
        add_tooltip(_reset_btn, "Clear the proposed renames list so you can change settings and run Analyze again")
        ctk.CTkLabel(row3, text="Reset clears the list so you can change settings and run Analyze or Preview again.", text_color="gray70").pack(side="left")

    def _reset_list(self):
        """Clear the proposed renames list so the user can change settings and run Analyze again."""
        self._proposals = []
        self._refresh_list()

    def _browse(self):
        path = filedialog.askdirectory(title="Select folder with images")
        if path:
            self._folder = Path(path)
            self._path_var.set(str(self._folder))
            self._proposals = []
            self._refresh_list()

    def _refresh_list(self):
        self._list_text.configure(state="normal")
        self._list_text.delete("1.0", "end")
        if not self._proposals:
            self._list_text.insert("1.0", "Select a folder, then Analyze (dry run) or Preview prepend only to see proposed names.")
        else:
            lines = [f"  {p.name}  →  {name}" for p, name in self._proposals]
            self._list_text.insert("1.0", "\n".join(lines))
        self._list_text.configure(state="disabled")

    def _analyze(self):
        if not self._folder or not self._folder.is_dir():
            messagebox.showinfo("Batch rename", "Select a folder first (Browse).")
            return
        files = [f for f in self._folder.iterdir() if f.is_file() and f.suffix.lower() in VALID_EXTENSIONS]
        if not files:
            messagebox.showwarning("Batch rename", "No .jpg, .png, or .webp images in that folder.")
            return
        get_vram_manager().ensure_state(State.CAPTIONING)
        tagger = get_tagger()
        if tagger.load_model() is None:
            messagebox.showerror("WD14", "Failed to load WD14 model. Check log (e.g. pandas, onnxruntime).")
            return
        threshold = self._threshold_var.get()
        max_tags = int(self._max_tags_var.get())
        omit_text = (self._omit_entry.get() or "").strip()
        omit_words: List[str] = []
        for part in omit_text.replace(",", " ").split():
            w = part.strip()
            if w:
                omit_words.append(w)
        prepend_text = (self._prepend_entry.get() or "").strip()
        prepend_words: List[str] = []
        for part in prepend_text.replace(",", " ").split():
            w = part.strip()
            if w:
                prepend_words.append(w)
        sorted_files = sorted(files)
        total = len(sorted_files)
        self._proposals = []
        self._analyze_btn.configure(state="disabled", text="Analyzing…")

        def work():
            from ui.app_main import set_progress, set_status
            proposals = []
            set_status(f"Analyzing {total} image(s)…", busy=True)
            for i, path in enumerate(sorted_files, 1):
                set_progress(i, total, f"Analyzing {i}/{total}: {path.name}")
                tags = tag_image(path, threshold=threshold)
                proposed_name = _propose_name(
                    path, tags, max_tags, omit_words=omit_words, prepend_words=prepend_words
                )
                proposals.append((path, proposed_name))
            set_status("Ready")
            return proposals

        def on_done(proposals):
            self._proposals = proposals
            self._analyze_btn.configure(state="normal", text="Analyze (dry run)")
            self._refresh_list()
            messagebox.showinfo("Dry run", f"Analyzed {len(proposals)} image(s). Review the list; click Apply renames to commit.")

        def run():
            try:
                proposals = work()
                self.after(0, lambda: on_done(proposals))
            except Exception as e:
                from ui.app_main import set_status
                set_status("Ready")
                self.after(0, lambda: self._analyze_btn.configure(state="normal", text="Analyze (dry run)"))
                self.after(0, lambda: messagebox.showerror("Analyze", str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _build_manual_list(self):
        """Build proposed renames using only the manual prepend (no AI analysis)."""
        if not self._folder or not self._folder.is_dir():
            messagebox.showinfo("Batch rename", "Select a folder first (Browse).")
            return
        files = [f for f in self._folder.iterdir() if f.is_file() and f.suffix.lower() in VALID_EXTENSIONS]
        if not files:
            messagebox.showwarning("Batch rename", "No .jpg, .png, or .webp images in that folder.")
            return
        prepend_text = (self._prepend_entry.get() or "").strip()
        prepend_words: List[str] = []
        for part in prepend_text.replace(",", " ").split():
            w = part.strip()
            if w:
                prepend_words.append(w)
        self._proposals = []
        for path in sorted(files):
            proposed_name = _propose_name(
                path, tags=[], max_tags=0, omit_words=None, prepend_words=prepend_words
            )
            self._proposals.append((path, proposed_name))
        self._refresh_list()
        messagebox.showinfo("Preview", f"List built for {len(self._proposals)} image(s) (prepend only, no analysis). Review and click Apply renames to commit.")

    def _build_simple_rename_list(self):
        """Build proposed renames using a fixed base name with an optional sequential suffix."""
        if not self._folder or not self._folder.is_dir():
            messagebox.showinfo("Simple rename", "Select a folder first (Browse).")
            return
        files = sorted([f for f in self._folder.iterdir() if f.is_file() and f.suffix.lower() in VALID_EXTENSIONS])
        if not files:
            messagebox.showwarning("Simple rename", "No .jpg, .png, or .webp images in that folder.")
            return
        base = (self._base_name_entry.get() or "").strip()
        if not base:
            messagebox.showinfo("Simple rename", "Enter a base name first.")
            return
        use_seq = self._seq_suffix_var.get()
        try:
            start = int(self._seq_start_entry.get().strip() or "1")
        except ValueError:
            start = 1
        pad = int(self._seq_pad_var.get())
        self._proposals = []
        for i, path in enumerate(files):
            if use_seq:
                stem = f"{base}_{str(start + i).zfill(pad)}"
            else:
                stem = base if len(files) == 1 else f"{base}_{str(start + i).zfill(pad)}"
            proposed_name = stem + path.suffix.lower()
            self._proposals.append((path, proposed_name))
        self._refresh_list()
        messagebox.showinfo("Preview", f"Simple rename preview for {len(self._proposals)} image(s). Review and click Apply renames to commit.")

    def _apply(self):
        if not self._proposals:
            messagebox.showinfo("Apply", "Run Analyze (dry run) or Preview prepend only first.")
            return
        if not messagebox.askyesno("Apply renames", f"Rename {len(self._proposals)} file(s) in the folder? This cannot be undone."):
            return
        errors = []
        for path, proposed_name in self._proposals:
            dest = path.parent / proposed_name
            if dest == path:
                continue
            if dest.exists():
                errors.append(f"{proposed_name} already exists")
                continue
            try:
                path.rename(dest)
            except Exception as e:
                errors.append(f"{path.name}: {e}")
        if errors:
            messagebox.showerror("Apply", "\n".join(errors[:10]) + ("\n..." if len(errors) > 10 else ""))
        else:
            messagebox.showinfo("Apply", "All files renamed.")
            self._proposals = []
            self._refresh_list()
