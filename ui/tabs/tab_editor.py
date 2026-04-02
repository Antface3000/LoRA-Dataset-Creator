"""Caption Editor Tab - The "Glass Box" dual-pane editor for Stage 3 captioning."""

import customtkinter as ctk
from pathlib import Path
from typing import List, Optional
from PIL import Image

from core.pipeline_manager import get_pipeline_manager
from core.ai.vram import get_vram_manager, State
from core.ai.tagger import tag_image, get_tagger
from core.ai.captioner import generate_caption, run_caption_batch_two_phase
from core.config import CAPTION_LLAMA_GGUF_PATH, CAPTION_FIND_REPLACE, CAPTION_TRIGGER_WORDS
import core.config as core_config
from core.data.file_handler import write_caption_file
from ui.components.tag_chip import TagChip


class EditorTab(ctk.CTkFrame):
    """Caption editor tab with dual-pane Glass Box interface."""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.pipeline_manager = get_pipeline_manager()
        self.vram_manager = get_vram_manager()
        
        # State
        self.current_image_path: Optional[Path] = None
        self.tags: List[str] = []
        self.caption: str = ""
        self.dirty_flag = False  # True if caption manually edited
        self.user_prompt = ""
        
        self.setup_ui()
        self.vram_manager.ensure_state(State.CAPTIONING)
    
    def setup_ui(self):
        """Setup dual-pane editor UI."""
        # Top controls
        control_frame = ctk.CTkFrame(self)
        control_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkButton(control_frame, text="Load Image", command=self.load_image).pack(side="left", padx=5)
        ctk.CTkButton(control_frame, text="Generate Caption", command=self.generate_caption_clicked).pack(side="left", padx=5)
        ctk.CTkButton(control_frame, text="Clear Dirty", command=self.clear_dirty).pack(side="left", padx=5)
        ctk.CTkButton(control_frame, text="Save Caption", command=self.save_caption_clicked).pack(side="left", padx=5)
        
        # Tag threshold (weight) slider
        ctk.CTkLabel(control_frame, text="Tag threshold:").pack(side="left", padx=(10, 2))
        self.tag_threshold_var = ctk.DoubleVar(value=0.5)
        ctk.CTkSlider(control_frame, from_=0.35, to=0.85, variable=self.tag_threshold_var, width=80).pack(side="left", padx=2)
        
        # Trigger words (appended to caption for LoRA)
        ctk.CTkLabel(control_frame, text="Trigger words:").pack(side="left", padx=(10, 2))
        self.trigger_entry = ctk.CTkEntry(control_frame, placeholder_text="e.g. mylora", width=120)
        self.trigger_entry.insert(0, CAPTION_TRIGGER_WORDS or "")
        self.trigger_entry.pack(side="left", padx=2)
        
        # Output format: Tags only / Natural language / Both
        ctk.CTkLabel(control_frame, text="Output:").pack(side="left", padx=(10, 2))
        self.output_format_var = ctk.StringVar(value="Natural language")
        output_menu = ctk.CTkOptionMenu(
            control_frame,
            variable=self.output_format_var,
            values=["Tags only", "Natural language", "Both"],
            width=140
        )
        output_menu.pack(side="left", padx=2)
        
        # User prompt input (expand with available space)
        ctk.CTkLabel(control_frame, text="Prompt:").pack(side="left", padx=5)
        self.prompt_entry = ctk.CTkEntry(control_frame, placeholder_text="Optional prompt…")
        self.prompt_entry.pack(side="left", padx=5, fill="x", expand=True)
        
        # Caption queue strip (resizable height)
        queue_frame = ctk.CTkFrame(self)
        queue_frame.pack(fill="x", padx=10, pady=(0, 5))
        self.queue_label = ctk.CTkLabel(queue_frame, text="Caption queue (0)", font=ctk.CTkFont(size=12, weight="bold"))
        self.queue_label.pack(side="left", padx=10, pady=5)
        ctk.CTkButton(queue_frame, text="Load next", width=90, command=self.load_next_from_queue).pack(side="left", padx=5, pady=5)
        ctk.CTkButton(queue_frame, text="Run batch", width=90, fg_color="#1f538d", command=self.run_batch_caption).pack(side="left", padx=5, pady=5)
        ctk.CTkButton(queue_frame, text="Clear queue", width=90, fg_color="gray", command=self.clear_caption_queue_clicked).pack(side="left", padx=5, pady=5)
        self.queue_list_frame = ctk.CTkScrollableFrame(queue_frame, height=80)
        self.queue_list_frame.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        self.refresh_queue_display()
        
        # Caption options: find/replace (one per line: find|replace)
        opts_frame = ctk.CTkFrame(self)
        opts_frame.pack(fill="x", padx=10, pady=(0, 5))
        ctk.CTkLabel(opts_frame, text="Find/replace (one per line: find|replace):", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=10, pady=(5, 2))
        self.find_replace_text = ctk.CTkTextbox(opts_frame, height=60, wrap="word")
        self.find_replace_text.pack(fill="x", padx=10, pady=(0, 5))
        init_fr = "\n".join(f"{a}|{b}" for a, b in (CAPTION_FIND_REPLACE or []))
        if init_fr:
            self.find_replace_text.insert("1.0", init_fr)
        
        # Main content - resizable grid: image row + tags/caption row
        content_frame = ctk.CTkFrame(self)
        content_frame.pack(fill="both", expand=True, padx=10, pady=10)
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_rowconfigure(0, weight=1)
        content_frame.grid_rowconfigure(1, weight=2)
        
        # Image preview (top row - resizes with window)
        image_frame = ctk.CTkFrame(content_frame)
        image_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 5))
        image_frame.grid_columnconfigure(0, weight=1)
        image_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(image_frame, text="Image Preview", font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, pady=5)
        self.image_label = ctk.CTkLabel(image_frame, text="No image loaded")
        self.image_label.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        
        # Bottom row: Tags and Caption panes (resize with window)
        bottom_frame = ctk.CTkFrame(content_frame)
        bottom_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(5, 10))
        bottom_frame.grid_columnconfigure(0, weight=1)
        bottom_frame.grid_columnconfigure(1, weight=1)
        bottom_frame.grid_rowconfigure(1, weight=1)
        
        # Left pane - Tags
        left_pane = ctk.CTkFrame(bottom_frame)
        left_pane.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 5), pady=10)
        left_pane.grid_columnconfigure(0, weight=1)
        left_pane.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(left_pane, text="Tags (Source of Truth)", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, pady=10)
        self.tag_container = ctk.CTkScrollableFrame(left_pane)
        self.tag_container.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 5))
        tag_input_frame = ctk.CTkFrame(left_pane)
        tag_input_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
        tag_input_frame.grid_columnconfigure(0, weight=1)
        self.tag_entry = ctk.CTkEntry(tag_input_frame, placeholder_text="Add tag...")
        self.tag_entry.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        self.tag_entry.bind("<Return>", lambda e: self.add_tag())
        ctk.CTkButton(tag_input_frame, text="Add", command=self.add_tag, width=60).grid(row=0, column=1, padx=5, pady=5)
        
        # Right pane - Caption
        right_pane = ctk.CTkFrame(bottom_frame)
        right_pane.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(5, 0), pady=10)
        right_pane.grid_columnconfigure(0, weight=1)
        right_pane.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(right_pane, text="Generated Caption", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, pady=10)
        self.caption_textbox = ctk.CTkTextbox(right_pane, wrap="word")
        self.caption_textbox.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 5))
        self.caption_textbox.bind("<KeyRelease>", self.on_caption_edit)
        self.dirty_indicator = ctk.CTkLabel(right_pane, text="", font=ctk.CTkFont(size=10))
        self.dirty_indicator.grid(row=2, column=0, pady=5)
        
        # Resize image preview when frame size changes (deferred + throttled to stop resize loops)
        image_frame.bind("<Configure>", self._on_image_frame_configure)
        self._image_frame_last_wh = (0, 0)
        self._image_configure_after_id = None
        self._image_last_redraw_time = 0.0
        self.current_profile = {}
    
    def apply_profile(self, profile: dict):
        """Apply current profile settings (e.g. default VLM prompt)."""
        self.current_profile = profile
        default_prompt = profile.get("vlm_prompt", "")
        self.prompt_entry.delete(0, "end")
        self.prompt_entry.insert(0, default_prompt)
    
    def _apply_caption_options_to_config(self):
        """Push trigger words and find/replace from UI to config so captioner uses them."""
        core_config.CAPTION_TRIGGER_WORDS = (self.trigger_entry.get() or "").strip()
        pairs = []
        for line in (self.find_replace_text.get("1.0", "end-1c") or "").strip().splitlines():
            line = line.strip()
            if not line:
                continue
            if "|" in line:
                find_s, _, replace_s = line.partition("|")
                pairs.append((find_s.strip(), replace_s.strip()))
            elif "->" in line:
                find_s, _, replace_s = line.partition("->")
                pairs.append((find_s.strip(), replace_s.strip()))
            else:
                continue
        core_config.CAPTION_FIND_REPLACE = pairs
    
    def load_image(self):
        """Load image for captioning. Uses current source folder as default if set."""
        from tkinter import filedialog
        initialdir = None
        if self.pipeline_manager.source_folder and self.pipeline_manager.source_folder.exists():
            initialdir = str(self.pipeline_manager.source_folder)
        file_path = filedialog.askopenfilename(
            initialdir=initialdir,
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.webp")]
        )
        if file_path:
            self.current_image_path = Path(file_path)
            self.tags = []
            self.caption = ""
            self.dirty_flag = False
            self.refresh_tags_display()
            self.caption_textbox.delete("1.0", "end")
            self.update_dirty_indicator()
            self.display_image()
    
    def _on_image_frame_configure(self, event):
        """Refresh image preview when the image frame is resized. Throttled to stop resize loops."""
        w, h = event.width, event.height
        if w < 50 or h < 50:
            return
        last_w, last_h = getattr(self, "_image_frame_last_wh", (0, 0))
        if abs(w - last_w) < 8 and abs(h - last_h) < 8:
            return
        self._image_frame_last_wh = (w, h)
        if not (self.current_image_path and self.current_image_path.exists()):
            return
        if self._image_configure_after_id is not None:
            self.after_cancel(self._image_configure_after_id)
        self._image_configure_after_id = self.after(100, self._deferred_display_image)

    def _deferred_display_image(self):
        """Run image redraw; throttle so we don't redraw more than once per 400ms to stop loops."""
        import time
        self._image_configure_after_id = None
        now = time.monotonic()
        if now - getattr(self, "_image_last_redraw_time", 0) < 0.4:
            return
        self._image_last_redraw_time = now
        self.display_image()

    def display_image(self):
        """Display the loaded image in the preview; size from last known frame size to avoid resize loops."""
        if not self.current_image_path or not self.current_image_path.exists():
            self.image_label.configure(image=None, text="No image loaded")
            return
        try:
            img = Image.open(self.current_image_path).convert("RGB")
            # Use last known frame size so we don't trigger new Configure by changing label size
            last_w, last_h = getattr(self, "_image_frame_last_wh", (0, 0))
            if last_w >= 100 and last_h >= 100:
                w, h = last_w, last_h
            else:
                try:
                    w = self.image_label.winfo_width() or 400
                    h = self.image_label.winfo_height() or 300
                    if w < 100:
                        w = 400
                    if h < 100:
                        h = 300
                except Exception:
                    w, h = 400, 300
            img.thumbnail((w, h), Image.Resampling.LANCZOS)
            if img.width == 0 or img.height == 0:
                img = img.resize((min(400, w), min(300, h)), Image.Resampling.LANCZOS)
            # CTkImage needs file path or PIL; CustomTkinter often supports size=
            ctk_image = ctk.CTkImage(light_image=img, dark_image=img, size=(img.width, img.height))
            self.image_label.configure(image=ctk_image, text="")
            self.image_label.image = ctk_image
        except Exception as e:
            self.image_label.configure(image=None, text=f"Error loading image: {e}")
    
    def _content_for_output_format(self) -> str:
        """Build caption textbox/save content from tags and caption per output format."""
        return self._build_content(self.tags, self.caption)

    def _build_content(self, tags: List[str], caption: str) -> str:
        """Build content string from tags and caption using current output format."""
        fmt = self.output_format_var.get()
        tags_str = ", ".join(tags) if tags else ""
        if fmt == "Tags only":
            return tags_str
        if fmt == "Natural language":
            return caption
        if fmt == "Both":
            if tags_str and caption:
                return tags_str + "\n\n" + caption
            return tags_str or caption
        return caption or tags_str
    
    def generate_caption_clicked(self):
        """Generate tags (if empty) then caption; show result per output format."""
        if not self.current_image_path:
            return
        
        self._apply_caption_options_to_config()
        self.user_prompt = self.prompt_entry.get()
        threshold = self.tag_threshold_var.get()
        
        try:
            # Step 1: Tags first (with threshold) — ensure WD14 is loaded
            if not self.tags:
                if get_tagger().load_model() is None:
                    from tkinter import messagebox
                    messagebox.showwarning(
                        "WD14 not loaded",
                        "WD14 tagger failed to load. Check the log for 'Failed to load WD14 model'. Using empty tags."
                    )
                self.tags = tag_image(self.current_image_path, threshold=threshold)
                self.refresh_tags_display()
            
            # Step 2: LLM caption from image + tags
            if not self.dirty_flag:
                self.caption = generate_caption(self.current_image_path, self.tags, self.user_prompt)
                self.dirty_flag = False
                self.update_dirty_indicator()
            
            # Step 3: Show in textbox according to output format
            content = self._content_for_output_format()
            self.caption_textbox.delete("1.0", "end")
            self.caption_textbox.insert("1.0", content)
        except Exception as e:
            import traceback
            error_msg = f"Error generating caption: {str(e)}\n{traceback.format_exc()}"
            print(error_msg)
            from tkinter import messagebox
            messagebox.showerror("Error", f"Failed to generate caption: {str(e)}")
    
    def refresh_tags_display(self):
        """Refresh tag chips display."""
        # Clear existing tags
        for widget in self.tag_container.winfo_children():
            widget.destroy()
        
        # Add tag chips
        for tag in self.tags:
            chip = TagChip(
                self.tag_container,
                tag,
                on_remove=self.remove_tag,
                on_click=None
            )
            chip.pack(fill="x", pady=2)
    
    def add_tag(self):
        """Add a new tag."""
        tag_text = self.tag_entry.get().strip()
        if tag_text and tag_text not in self.tags:
            self.tags.append(tag_text)
            self.tag_entry.delete(0, "end")
            self.refresh_tags_display()
            
            # Re-generate caption if not dirty
            if not self.dirty_flag and self.current_image_path:
                self.generate_caption_clicked()
    
    def remove_tag(self, tag: str):
        """Remove a tag."""
        if tag in self.tags:
            self.tags.remove(tag)
            self.refresh_tags_display()
            
            # Re-generate caption if not dirty
            if not self.dirty_flag and self.current_image_path:
                self.generate_caption_clicked()
    
    def on_caption_edit(self, event):
        """Handle caption text edit - set dirty flag."""
        self.dirty_flag = True
        self.caption = self.caption_textbox.get("1.0", "end-1c")
        self.update_dirty_indicator()
    
    def clear_dirty(self):
        """Clear dirty flag and re-generate caption."""
        self.dirty_flag = False
        self.update_dirty_indicator()
        if self.current_image_path:
            self.generate_caption_clicked()
    
    def update_dirty_indicator(self):
        """Update dirty flag visual indicator."""
        if self.dirty_flag:
            self.dirty_indicator.configure(
                text="⚠️ Caption manually edited (auto-generation disabled)",
                text_color="orange"
            )
            self.caption_textbox.configure(border_color="orange", border_width=2)
        else:
            self.dirty_indicator.configure(text="", text_color="gray")
            self.caption_textbox.configure(border_color="gray", border_width=1)
    
    def save_caption_clicked(self):
        """Save caption/tags to same-named .txt next to current image (or chosen path)."""
        content = self._content_for_output_format()
        if not content.strip():
            from tkinter import messagebox
            messagebox.showinfo("Save Caption", "Nothing to save. Generate tags/caption first.")
            return
        if self.current_image_path and self.current_image_path.exists():
            txt_path = self.current_image_path.with_suffix(".txt")
            write_caption_file(txt_path, content)
            from tkinter import messagebox
            messagebox.showinfo("Save Caption", f"Saved to:\n{txt_path}")
        else:
            from tkinter import filedialog, messagebox
            initialdir = None
            if self.pipeline_manager.output_folder and self.pipeline_manager.output_folder.exists():
                initialdir = str(self.pipeline_manager.output_folder)
            path = filedialog.asksaveasfilename(
                initialdir=initialdir,
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt")]
            )
            if path:
                write_caption_file(Path(path), content)
                messagebox.showinfo("Save Caption", f"Saved to:\n{path}")

    def refresh_queue_display(self):
        """Refresh the caption queue list and count."""
        queue = self.pipeline_manager.get_caption_queue()
        self.queue_label.configure(text=f"Caption queue ({len(queue)})")
        for w in self.queue_list_frame.winfo_children():
            w.destroy()
        for path in queue:
            ctk.CTkLabel(self.queue_list_frame, text=path.name, anchor="w").pack(fill="x")

    def load_next_from_queue(self):
        """Load the next image from the caption queue into the editor."""
        from tkinter import messagebox
        path = self.pipeline_manager.pop_next_from_caption_queue()
        if not path:
            messagebox.showinfo("Queue", "Caption queue is empty.")
            self.refresh_queue_display()
            return
        self.current_image_path = path
        self.tags = []
        self.caption = ""
        self.dirty_flag = False
        self.refresh_tags_display()
        self.caption_textbox.delete("1.0", "end")
        self.update_dirty_indicator()
        self.display_image()
        self.refresh_queue_display()

    def run_batch_caption(self):
        """Process entire caption queue using current profile + options.

        Uses two-phase flow when Llama is configured: run vision (tag + describe)
        on all images, unload vision models, then run Llama on all to avoid VRAM bottleneck.
        """
        from tkinter import messagebox
        paths = self.pipeline_manager.get_caption_queue()
        if not paths:
            messagebox.showinfo("Run batch", "Caption queue is empty.")
            return
        threshold = self.tag_threshold_var.get()
        prompt = self.prompt_entry.get()
        self._apply_caption_options_to_config()
        use_two_phase = CAPTION_LLAMA_GGUF_PATH.exists() and CAPTION_LLAMA_GGUF_PATH.is_file()
        try:
            # Eager-load WD14 so we surface load failure before processing
            if get_tagger().load_model() is None:
                messagebox.showerror(
                    "WD14 not loaded",
                    "WD14 tagger failed to load. Check the log for 'Failed to load WD14 model' (e.g. network, ONNX, HuggingFace). Cannot run batch."
                )
                return
            if use_two_phase:
                self.queue_label.configure(text="Phase 1: Tag + vision for all images…")
                self.update_idletasks()
                results = run_caption_batch_two_phase(paths, tag_threshold=threshold, user_prompt=prompt)
                self.queue_label.configure(text="Writing caption files…")
                self.update_idletasks()
                for path, tags, caption in results:
                    content = self._build_content(tags, caption)
                    write_caption_file(path.with_suffix(".txt"), content)
                self.pipeline_manager.clear_caption_queue()
                self.refresh_queue_display()
                messagebox.showinfo("Run batch", f"Captioning complete. Processed {len(results)} image(s).")
            else:
                done = 0
                while True:
                    path = self.pipeline_manager.pop_next_from_caption_queue()
                    if not path:
                        break
                    self.queue_label.configure(text=f"Caption queue ({len(self.pipeline_manager.get_caption_queue())}) — processing {path.name}…")
                    self.update_idletasks()
                    tags = tag_image(path, threshold=threshold)
                    caption = generate_caption(path, tags, prompt)
                    content = self._build_content(tags, caption)
                    write_caption_file(path.with_suffix(".txt"), content)
                    done += 1
                    self.refresh_queue_display()
                messagebox.showinfo("Run batch", f"Captioning complete. Processed {done} image(s).")
        except Exception as e:
            import traceback
            messagebox.showerror("Run batch error", f"{str(e)}\n{traceback.format_exc()}")

    def clear_caption_queue_clicked(self):
        """Clear the caption queue."""
        self.pipeline_manager.clear_caption_queue()
        self.refresh_queue_display()
