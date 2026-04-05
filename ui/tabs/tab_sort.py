"""Sorting/Cropping Tab - Filter/Sort/Crop Interface (VIEW ONLY, delegates to core)."""

import customtkinter as ctk
from tkinter import messagebox
from pathlib import Path
from PIL import Image
from typing import Optional, Callable

from core.pipeline_manager import get_pipeline_manager
from core.ai.cropper import resize_to_bucket
from core.ai.vram import get_vram_manager, State
from core.data.file_handler import load_image_files, save_cropped_image_flat, create_output_structure
from core.config import BUCKETS
from ui.tabs.tab_sort_canvas import CanvasHelper
from ui.tabs.tab_sort_quality import run_quality_filter_batch
from ui.tabs.tab_sort_display import create_crop_overlay
from ui.tabs.tab_sort_image import load_and_process_image
from ui.tabs.tab_sort_ui import create_canvas_frame, create_control_panel, create_top_controls, select_folder_dialog
from ui.tabs.tab_sort_handlers import handle_canvas_click, handle_canvas_drag
from ui.tooltip import add_tooltip


class SortTab(ctk.CTkFrame):
    """Sorting and cropping tab - UI only, delegates to core modules."""
    
    def __init__(self, parent, on_last_image: Optional[Callable[[], None]] = None,
                 on_back: Optional[Callable[[], None]] = None):
        super().__init__(parent)
        self.pipeline_manager = get_pipeline_manager()
        self.vram_manager = get_vram_manager()
        self.on_last_image = on_last_image
        self.on_back = on_back

        # State
        self.source_folder: Optional[Path] = None
        self.output_folder: Optional[Path] = None
        self.image_files: list[Path] = []
        self.current_index = 0
        self.original_image: Optional[Image.Image] = None
        self.current_photo = None
        
        # Crop state
        self.crop_x1, self.crop_y1, self.crop_x2, self.crop_y2 = 0, 0, 0, 0
        self.drag_mode = None
        self.drag_start_x, self.drag_start_y = 0, 0
        self.current_bucket = 'square'
        self.padding_margin = 50
        self.person_confidence = 0.15
        self.auto_bucket_enabled = False
        self.canvas_helper = None
        
        self.setup_ui()
        self.vram_manager.ensure_state(State.CROPPING)
    
    def setup_ui(self):
        """Setup UI components."""
        # Top controls
        _, top_widgets = create_top_controls(
            self, self.select_source, self.select_output, self.run_quality_filter
        )
        self.blur_threshold_var = top_widgets['blur_threshold_var']
        self.aesthetic_threshold_var = top_widgets['aesthetic_threshold_var']
        self.dry_run_var = top_widgets['dry_run_var']
        self.status_label = top_widgets['status_label']
        
        # Main content
        content_frame = ctk.CTkFrame(self)
        content_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Left: Image canvas
        self.canvas, _ = create_canvas_frame(content_frame)
        
        # Right: Controls
        _, control_widgets = create_control_panel(content_frame)
        self.bucket_var = control_widgets['bucket_var']
        self.bucket_var.trace_add("write", lambda *args: self.on_bucket_change())
        self.crop_size_label = control_widgets['crop_size_label']
        control_widgets['prev_button'].configure(command=self.prev_image)
        control_widgets['save_button'].configure(command=self.save_and_next)
        control_widgets['skip_button'].configure(command=self.skip_image)
        control_widgets['auto_crop_button'].configure(command=self.run_auto_crop_all)
        self._back_button = control_widgets.get('back_button')

        # Back button at the bottom of the tab (navigates to Wizard tab)
        nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        nav_frame.pack(fill="x", padx=10, pady=(0, 8))
        _back_wiz_btn = ctk.CTkButton(nav_frame, text="← Back to Wizard", width=140,
                                      command=self._go_back)
        _back_wiz_btn.pack(side="left")
        add_tooltip(_back_wiz_btn, "Switch to the Wizard tab")

        # Canvas bindings
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        
        # Profile-driven settings (updated by app_main.load_profile_settings)
        self.current_profile = {}
    
    def _go_back(self):
        """Invoke the on_back callback if one was provided."""
        if self.on_back:
            self.on_back()

    def apply_profile(self, profile: dict):
        """Apply current profile settings (thresholds, padding, confidence)."""
        self.current_profile = profile
        qt = profile.get("quality_thresholds") or {}
        self.blur_threshold_var.set(qt.get("min_laplacian_variance", 100.0))
        self.aesthetic_threshold_var.set(qt.get("min_aesthetic_score", 5.0))
        self.padding_margin = int(profile.get("padding_margin", 50))
        self.person_confidence = float(profile.get("person_confidence", 0.15))
        self.auto_bucket_enabled = bool(profile.get("auto_bucket", False))
    
    def select_source(self):
        """Select source folder."""
        folder = select_folder_dialog("Select Source Folder")
        if folder:
            self.source_folder = Path(folder)
            self.pipeline_manager.source_folder = self.source_folder
            self.image_files = load_image_files(self.source_folder)
            self.current_index = 0
            if self.image_files:
                self.load_current_image()
    
    def select_output(self):
        """Select output folder."""
        folder = select_folder_dialog("Select Output Folder")
        if folder:
            self.output_folder = Path(folder)
            self.pipeline_manager.output_folder = self.output_folder
            create_output_structure(self.output_folder)
            if self.image_files:
                self.load_current_image()
    
    def run_quality_filter(self):
        """Run quality filter batch processing."""
        if not self.source_folder:
            messagebox.showwarning("Warning", "Please select a source folder first.")
            return
        
        blur_threshold = self.blur_threshold_var.get()
        aesthetic_threshold = self.aesthetic_threshold_var.get()
        dry_run = self.dry_run_var.get()
        mode = "aesthetic"
        
        image_files = load_image_files(self.source_folder)
        if not image_files:
            messagebox.showinfo("Info", "No images found in source folder.")
            return
        
        if not dry_run:
            confirm = messagebox.askyesno(
                "Confirm Quality Filter",
                f"Run quality filter on {len(image_files)} images?\n\n"
                f"Mode: {'Aesthetic' if mode == 'aesthetic' else 'Blur'}\n"
                f"This will move rejected images to reject folders."
            )
            if not confirm:
                return
        
        def status_callback(text):
            self.status_label.configure(text=text)
            self.update()
        
        passed_count, rejected_count = run_quality_filter_batch(
            self.source_folder, self.pipeline_manager, blur_threshold,
            aesthetic_threshold, dry_run, mode, status_callback
        )
        
        if not dry_run:
            self.image_files = load_image_files(self.source_folder)
            if self.image_files:
                self.current_index = 0
                self.load_current_image()
        
        result_msg = f"[DRY RUN] " if dry_run else ""
        result_msg += f"Quality filter complete: {passed_count} passed, {rejected_count} rejected"
        self.status_label.configure(text=result_msg)
        messagebox.showinfo(
            "Quality Filter Complete" if not dry_run else "Dry Run Complete",
            f"{'[DRY RUN] ' if dry_run else ''}Processed {len(image_files)} images:\n\n"
            f"✓ {'Would Keep' if dry_run else 'Passed'}: {passed_count}\n"
            f"✗ {'Would Reject' if dry_run else 'Rejected'}: {rejected_count}"
        )
    
    def on_bucket_change(self):
        """Handle bucket change: recompute crop box for new aspect ratio and refresh."""
        self.current_bucket = self.bucket_var.get()
        if self.original_image is not None and self.image_files and self.current_index < len(self.image_files):
            image_path = self.image_files[self.current_index]
            _, _, _, crop_coords = load_and_process_image(
                image_path,
                self.vram_manager,
                self.person_confidence,
                self.padding_margin,
                self.current_bucket,
                auto_bucket_enabled=self.auto_bucket_enabled,
            )
            self.crop_x1, self.crop_y1, self.crop_x2, self.crop_y2 = crop_coords
        self.update_display()
    
    def load_current_image(self):
        """Load current image."""
        if self.current_index >= len(self.image_files):
            return
        
        image_path = self.image_files[self.current_index]
        
        # Load and process using helper
        self.original_image, person, selected_bucket, crop_coords = load_and_process_image(
            image_path,
            self.vram_manager,
            self.person_confidence,
            self.padding_margin,
            self.current_bucket,
            auto_bucket_enabled=self.auto_bucket_enabled,
        )
        
        # Update state
        self.current_bucket = selected_bucket
        self.bucket_var.set(selected_bucket)
        self.crop_x1, self.crop_y1, self.crop_x2, self.crop_y2 = crop_coords
        
        # Update canvas helper
        self.canvas_helper = CanvasHelper(self.canvas, self.original_image)
        
        self.update_display()
    
    def update_display(self):
        """Update canvas display with crop overlay."""
        if not self.original_image:
            return
        
        canvas_width  = self.canvas.winfo_width()  if self.canvas.winfo_width()  > 1 else 800
        canvas_height = self.canvas.winfo_height() if self.canvas.winfo_height() > 1 else 600
        
        # Create overlay using helper
        self.current_photo = create_crop_overlay(
            self.original_image,
            self.crop_x1, self.crop_y1, self.crop_x2, self.crop_y2,
            canvas_width, canvas_height
        )
        
        self.canvas.delete("all")
        self.canvas.create_image(canvas_width // 2, canvas_height // 2, anchor="center", image=self.current_photo)
        
        # Update crop info
        self.crop_size_label.configure(text=f"Crop: {int(self.crop_x2-self.crop_x1)}x{int(self.crop_y2-self.crop_y1)}")
    
    def on_canvas_click(self, event):
        """Handle canvas click: set drag mode and grab so drag continues past canvas border."""
        self.drag_mode, self.drag_start_x, self.drag_start_y = handle_canvas_click(
            event, self.canvas, self.canvas_helper,
            self.crop_x1, self.crop_y1, self.crop_x2, self.crop_y2
        )
        if self.drag_mode:
            try:
                self.canvas.grab_set()
            except Exception:
                pass
    
    def on_canvas_drag(self, event):
        """Handle canvas drag."""
        new_coords = handle_canvas_drag(
            event, self.canvas, self.canvas_helper, self.original_image,
            self.drag_mode, self.drag_start_x, self.drag_start_y,
            self.crop_x1, self.crop_y1, self.crop_x2, self.crop_y2
        )
        
        if new_coords != (self.crop_x1, self.crop_y1, self.crop_x2, self.crop_y2):
            self.crop_x1, self.crop_y1, self.crop_x2, self.crop_y2 = new_coords
            if self.drag_mode == "move" and self.canvas_helper:
                canvas_x = self.canvas.canvasx(event.x)
                canvas_y = self.canvas.canvasy(event.y)
                self.drag_start_x, self.drag_start_y = self.canvas_helper.canvas_to_image_coords(canvas_x, canvas_y)
            self.update_display()
    
    def on_canvas_release(self, event):
        """Handle canvas release: clear drag mode and release grab."""
        try:
            self.canvas.grab_release()
        except Exception:
            pass
        self.drag_mode = None
    
    def save_and_next(self):
        """Save crop and move to next."""
        if not self.original_image or not self.output_folder:
            messagebox.showwarning("Warning", "Please select output folder first.")
            return
        if not self.image_files or self.current_index >= len(self.image_files):
            return
        try:
            crop_coords = (int(self.crop_x1), int(self.crop_y1), int(self.crop_x2), int(self.crop_y2))
            if crop_coords[2] <= crop_coords[0] or crop_coords[3] <= crop_coords[1]:
                messagebox.showerror("Error", "Invalid crop region.")
                return
            cropped = self.original_image.crop(crop_coords)
            resized = resize_to_bucket(cropped, self.current_bucket)
            saved_path = save_cropped_image_flat(resized, self.output_folder, self.current_bucket, self.image_files[self.current_index].stem)
            self.pipeline_manager.add_to_caption_queue(saved_path)
            self.current_index += 1
            if self.current_index >= len(self.image_files):
                if self.on_last_image:
                    self.on_last_image()
                return
            self.load_current_image()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save image: {str(e)}")
    
    def prev_image(self):
        """Go back to the previous image."""
        if not self.image_files or self.current_index <= 0:
            return
        self.current_index -= 1
        self.load_current_image()

    def skip_image(self):
        """Skip current image."""
        if not self.image_files:
            return
        self.current_index += 1
        if self.current_index < len(self.image_files):
            self.load_current_image()
        else:
            if self.on_last_image:
                self.on_last_image()
            messagebox.showinfo("Complete", "All images have been processed!")

    def run_auto_crop_all(self):
        """Auto-crop all images in source folder and add to caption queue."""
        source = self.pipeline_manager.source_folder or self.source_folder
        output = self.pipeline_manager.output_folder or self.output_folder
        if not source or not output:
            messagebox.showwarning("Warning", "Please select source and output folders first.")
            return
        files = load_image_files(source)
        if not files:
            messagebox.showwarning("Warning", "No images found in source folder.")
            return
        bucket = self.bucket_var.get() if hasattr(self, 'bucket_var') else self.current_bucket
        total = len(files)
        self.status_label.configure(text=f"Auto crop starting — {total} image(s)…")

        def work():
            from ui.app_main import set_status, set_progress
            set_status(f"Auto-cropping {total} image(s)…", busy=True)
            outputs = self.pipeline_manager.process_stage2_cropping_batch(
                files,
                output,
                bucket=bucket,
                confidence=self.person_confidence,
                padding=self.padding_margin,
                auto_bucket=self.auto_bucket_enabled,
                yolo_batch_size=8,
                progress_callback=lambda i: set_progress(i, total, f"Cropping {i}/{total}…"),
            )
            for out_path in outputs:
                self.pipeline_manager.add_to_caption_queue(out_path)
            set_status("Ready")
            return len(outputs)

        def on_done(queued):
            self.status_label.configure(text=f"Auto crop complete. {queued} image(s) queued.")
            messagebox.showinfo("Auto crop complete", f"Cropped {queued} image(s). Switch to the Wizard tab to continue.")

        def on_error(e):
            from ui.app_main import set_status
            set_status("Ready")
            self.status_label.configure(text=f"Auto crop error: {e}")
            messagebox.showerror("Auto crop error", f"Failed batch crop: {e}")

        def run():
            try:
                queued = work()
                self.after(0, lambda: on_done(queued))
            except Exception as e:
                self.after(0, lambda: on_error(e))

        import threading
        threading.Thread(target=run, daemon=True).start()
