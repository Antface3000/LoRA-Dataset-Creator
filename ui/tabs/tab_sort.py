"""Sorting/Cropping Tab - Filter/Sort/Crop Interface (VIEW ONLY, delegates to core)."""

import shutil
import threading
import customtkinter as ctk
from tkinter import messagebox
from pathlib import Path
from PIL import Image
from typing import Optional, Callable

from core.pipeline_manager import get_pipeline_manager
from core.ai.cropper import resize_to_bucket, resize_letterbox
from core.ai.vram import get_vram_manager, State
from core.data.file_handler import load_image_files, save_cropped_image_flat, create_output_structure
from core.config import BUCKETS
from ui.tabs.tab_sort_canvas import CanvasHelper
from ui.tabs.tab_sort_quality import run_quality_filter_batch
from ui.tabs.tab_sort_display import create_crop_overlay, create_plain_display
from ui.tabs.tab_sort_image import load_and_process_image
from ui.tabs.tab_sort_ui import create_canvas_frame, create_control_panel, create_top_controls, select_folder_dialog
from ui.tabs.tab_sort_handlers import handle_canvas_click, handle_canvas_drag
from ui.tooltip import add_tooltip
from core.ai.nudenet_detector import (
    detect_body_parts, detect_all_body_parts, box_to_coords, CLASS_SUFFIXES,
)


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
        self._current_person = None  # cached YOLO result for the loaded image
        self.padding_margin = 50
        self.person_confidence = 0.15
        self.auto_bucket_enabled = False
        self.canvas_helper = None
        self._nudenet_stop_event = threading.Event()

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
        self.skip_done_var = control_widgets['skip_done_var']
        self.skip_done_var.trace_add("write", lambda *args: self._reload_image_list())
        control_widgets['prev_button'].configure(command=self.prev_image)
        control_widgets['save_button'].configure(command=self.save_and_next)
        control_widgets['skip_button'].configure(command=self.skip_image)
        self._back_button = control_widgets.get('back_button')
        # Smart Detect wiring
        self.wm_threshold_var = control_widgets['wm_threshold_var']
        self._wm_scan_btn = control_widgets['wm_scan_btn']
        self._wm_scan_btn.configure(command=self.run_watermark_scan)
        self.body_part_vars = control_widgets['body_part_vars']
        control_widgets['bp_detect_btn'].configure(command=self.run_body_part_detect_current)
        control_widgets['smart_crop_btn'].configure(command=self.run_smart_crop_batch)
        self._btn_smart_stop = control_widgets['smart_stop_btn']
        self._btn_smart_stop.configure(command=self.run_smart_crop_stop)
        self._nudenet_section = control_widgets['nudenet_section']
        self._nudenet_section_review = control_widgets['nudenet_section_review']
        self.nudenet_context_scale = control_widgets['nudenet_context_scale_var']
        self.apply_nudenet_visibility()
        # YOLO margin slider — live-updates the crop box for the current image
        self._yolo_margin_var = control_widgets['yolo_margin_var']
        self._yolo_margin_var.trace_add("write", self._on_yolo_margin_change)
        # Minimum crop size — images below this are passed through without cropping
        self._min_crop_px_var = control_widgets['min_crop_px_var']
        self._min_crop_px_var.trace_add("write", self._on_min_crop_px_change)

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
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        
        # Profile-driven settings (updated by app_main.load_profile_settings)
        self.current_profile = {}
    
    def _on_yolo_margin_change(self, *_):
        """Live-update the crop box when the YOLO margin slider moves."""
        self.padding_margin = int(self._yolo_margin_var.get())
        # Recompute crop box immediately if an image is loaded
        if self.original_image is not None and self.current_bucket != "no_crop":
            self.on_bucket_change()

    def _on_min_crop_px_change(self, *_):
        """Persist min_crop_px to the current profile when the slider moves."""
        try:
            from core.data.profiles import get_profiles_manager
            pm = get_profiles_manager()
            name = pm.config.get("current_profile", "User settings")
            profile = pm.get_current_profile()
            profile["min_crop_px"] = int(self._min_crop_px_var.get())
            pm.save_profile(name, profile)
        except Exception:
            pass

    def apply_nudenet_visibility(self):
        """Show or hide NudeNet controls based on the current profile setting."""
        from core.data.profiles import get_profiles_manager
        enabled = bool(get_profiles_manager().get_current_profile().get("enable_nudenet", False))
        if enabled:
            self._nudenet_section.pack(fill="x", padx=10, pady=(0, 4))
            self._nudenet_section_review.pack(fill="x", padx=10, pady=(0, 4))
        else:
            self._nudenet_section.pack_forget()
            self._nudenet_section_review.pack_forget()

    def _go_back(self):
        """Invoke the on_back callback if one was provided."""
        if self.on_back:
            self.on_back()

    def _get_remaining_files(self, files: list) -> list:
        """Filter out source images already present in the output folder.

        Only applied when the 'Skip already cropped' checkbox is checked and
        an output folder is known.
        """
        if not getattr(self, 'skip_done_var', None) or not self.skip_done_var.get():
            return files
        out = self.output_folder or self.pipeline_manager.output_folder
        if not out:
            return files
        from core.data.file_handler import get_already_cropped_stems
        done = get_already_cropped_stems(out)
        return [f for f in files if f.stem not in done]

    def _reload_image_list(self):
        """Re-scan the source folder and apply the current skip filter.

        Called when the 'Skip already cropped' checkbox is toggled so the list
        updates instantly without requiring a new folder selection.
        """
        src = self.source_folder or self.pipeline_manager.source_folder
        if not src:
            return
        all_files = load_image_files(src)
        filtered = self._get_remaining_files(all_files)
        self.image_files = filtered
        self.current_index = 0
        total = len(all_files)
        remaining = len(filtered)
        skipped = total - remaining
        if skipped:
            self.status_label.configure(
                text=f"{remaining} remaining  ({skipped} already cropped)"
            )
        else:
            self.status_label.configure(text=f"{remaining} image(s) to process")
        if self.image_files:
            self.load_current_image()
        else:
            self.original_image = None
            self.canvas.delete("all")

    def apply_profile(self, profile: dict):
        """Apply current profile settings (thresholds, padding, confidence)."""
        self.current_profile = profile
        qt = profile.get("quality_thresholds") or {}
        self.blur_threshold_var.set(qt.get("min_laplacian_variance", 100.0))
        self.aesthetic_threshold_var.set(qt.get("min_aesthetic_score", 5.0))
        self.padding_margin = int(profile.get("padding_margin", 50))
        # Sync the slider to the profile value without triggering the live trace
        if hasattr(self, '_yolo_margin_var'):
            self._yolo_margin_var.set(float(self.padding_margin))
        self.person_confidence = float(profile.get("person_confidence", 0.15))
        self.auto_bucket_enabled = bool(profile.get("auto_bucket", False))
        if hasattr(self, '_min_crop_px_var'):
            self._min_crop_px_var.set(int(profile.get("min_crop_px", 512)))
    
    def select_source(self):
        """Select source folder."""
        folder = select_folder_dialog("Select Source Folder")
        if folder:
            self.source_folder = Path(folder)
            self.pipeline_manager.source_folder = self.source_folder
            all_files = load_image_files(self.source_folder)
            self.image_files = self._get_remaining_files(all_files)
            self.current_index = 0
            total = len(all_files)
            remaining = len(self.image_files)
            skipped = total - remaining
            if skipped:
                self.status_label.configure(
                    text=f"{remaining} remaining  ({skipped} already cropped)"
                )
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
        """Handle bucket change: recompute crop box using cached person, no YOLO re-run."""
        new_bucket = self.bucket_var.get()
        self.current_bucket = new_bucket
        if self.original_image is not None and new_bucket != "no_crop":
            from core.ai.cropper import calculate_crop_box
            crop_coords = calculate_crop_box(
                self.original_image,
                self._current_person,
                new_bucket,
                self.padding_margin,
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

        # Cache person so on_bucket_change can recalculate without re-running YOLO
        self._current_person = person

        # Update state
        self.current_bucket = selected_bucket
        self.bucket_var.set(selected_bucket)
        self.crop_x1, self.crop_y1, self.crop_x2, self.crop_y2 = crop_coords
        
        # Update canvas helper
        self.canvas_helper = CanvasHelper(self.canvas, self.original_image)

        # Defer the draw by one event-loop tick so the canvas has been mapped
        # and winfo_width/height return the real pixel dimensions.
        self.after(0, self.update_display)
    
    def _on_canvas_resize(self, event):
        """Debounce canvas Configure events to avoid spamming redraws during resize."""
        if hasattr(self, '_resize_after_id'):
            self.after_cancel(self._resize_after_id)
        self._resize_after_id = self.after(50, self._do_canvas_resize)

    def _do_canvas_resize(self):
        """Redraw after the canvas has settled at its new size."""
        if self.original_image is not None:
            self.update_display()

    def update_display(self):
        """Update canvas display with crop overlay (or plain image for no-crop)."""
        if not self.original_image:
            return

        canvas_width  = self.canvas.winfo_width()  if self.canvas.winfo_width()  > 1 else 800
        canvas_height = self.canvas.winfo_height() if self.canvas.winfo_height() > 1 else 600

        if self.current_bucket == "no_crop":
            self.current_photo = create_plain_display(
                self.original_image, canvas_width, canvas_height
            )
            self.crop_size_label.configure(
                text=f"No crop  ({self.original_image.width}×{self.original_image.height})"
            )
        else:
            self.current_photo = create_crop_overlay(
                self.original_image,
                self.crop_x1, self.crop_y1, self.crop_x2, self.crop_y2,
                canvas_width, canvas_height
            )
            self.crop_size_label.configure(
                text=f"Crop: {int(self.crop_x2-self.crop_x1)}×{int(self.crop_y2-self.crop_y1)}"
            )

        self.canvas.delete("all")
        self.canvas.create_image(canvas_width // 2, canvas_height // 2, anchor="center", image=self.current_photo)
    
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
        # Resolve output folder: prefer the tab-local one, fall back to the
        # pipeline manager's folder (set via the Wizard).
        effective_output = self.output_folder or self.pipeline_manager.output_folder
        if not self.original_image or not effective_output:
            messagebox.showwarning("Warning", "Please select an output folder first.")
            return
        if not self.image_files or self.current_index >= len(self.image_files):
            return
        try:
            src_path = self.image_files[self.current_index]

            if self.current_bucket == "no_crop":
                # Pass through with a "nocrop_" prefix so the stem detector
                # can always identify it regardless of file extension.
                dest = Path(effective_output) / f"nocrop_{src_path.name}"
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(src_path, dest)
                except shutil.SameFileError:
                    pass  # already in the right place
                saved_path = dest
            else:
                crop_coords = (int(self.crop_x1), int(self.crop_y1), int(self.crop_x2), int(self.crop_y2))
                if crop_coords[2] <= crop_coords[0] or crop_coords[3] <= crop_coords[1]:
                    messagebox.showerror("Error", "Invalid crop region.")
                    return
                cropped = self.original_image.crop(crop_coords)
                resized = resize_to_bucket(cropped, self.current_bucket)
                saved_path = save_cropped_image_flat(
                    resized, effective_output, self.current_bucket, src_path.stem
                )

            self.pipeline_manager.add_to_caption_queue(saved_path)

            # Reset bucket to auto-detect for the next image so "no_crop"
            # on one image does not silently carry over to the next.
            self.current_bucket = "square"

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
        # Reset bucket so auto-detection runs fresh on the next image.
        self.current_bucket = "square"
        self.current_index += 1
        if self.current_index < len(self.image_files):
            self.load_current_image()
        else:
            if self.on_last_image:
                self.on_last_image()
            messagebox.showinfo("Complete", "All images have been processed!")

    def run_smart_crop_batch(self):
        """Unified smart crop: YOLO finds the person (outer boundary), NudeNet focuses
        on selected body parts within that boundary.  No-person or too-small images are
        copied as nocrop_ passthrough.  If no body-part classes are checked the batch
        runs in YOLO-only mode."""
        source = self.pipeline_manager.source_folder or self.source_folder
        effective_output = self.pipeline_manager.output_folder or self.output_folder
        if not source or not effective_output:
            messagebox.showwarning("Warning", "Please select source and output folders first.")
            return

        files = load_image_files(source)
        if not files:
            messagebox.showwarning("Warning", "No images found in source folder.")
            return
        files = self._get_remaining_files(files)
        if not files:
            messagebox.showinfo("Smart Crop", "All images have already been processed. Nothing to do.")
            return

        target_classes = self._get_selected_nudenet_classes()   # empty = YOLO-only mode
        bucket = self.current_bucket if self.current_bucket != "no_crop" else "square"
        total = len(files)
        context_scale = self.nudenet_context_scale.get() if hasattr(self, 'nudenet_context_scale') else 2.0
        min_px = int(self._min_crop_px_var.get()) if hasattr(self, '_min_crop_px_var') else 0
        padding = self.padding_margin

        # Reset stop event and enable Stop button
        self._nudenet_stop_event.clear()
        if hasattr(self, '_btn_smart_stop'):
            self._btn_smart_stop.configure(state="normal")

        def work():
            from ui.app_main import set_status, set_progress
            from core.ai.cropper import detect_person

            mode = f"body-part focus ({len(target_classes)} class(es))" if target_classes else "YOLO person crop"
            set_status(f"Smart crop [{mode}]: {total} image(s)…", busy=True)

            yolo_model = self.vram_manager.load_yolo()
            output_dir = Path(effective_output)
            output_dir.mkdir(parents=True, exist_ok=True)

            cropped_count = 0
            passthrough_count = 0
            stopped = False

            def _passthrough(img_path: Path):
                dest = output_dir / f"nocrop_{img_path.name}"
                if not dest.exists():
                    try:
                        shutil.copy2(img_path, dest)
                    except shutil.SameFileError:
                        pass
                self.pipeline_manager.add_to_caption_queue(dest)

            for i, img_path in enumerate(files):
                # --- STOP CHECK 1 (between images) ---
                if self._nudenet_stop_event.is_set():
                    stopped = True
                    break

                set_progress(i + 1, total, f"{i + 1}/{total}: {img_path.name}")
                try:
                    img = Image.open(img_path)
                    img.load()
                    iw, ih = img.width, img.height

                    # Step 2: min-dimension passthrough
                    if min_px > 0 and (iw < min_px or ih < min_px):
                        _passthrough(img_path)
                        passthrough_count += 1
                        continue

                    # --- STOP CHECK 2 (before slow YOLO call) ---
                    if self._nudenet_stop_event.is_set():
                        stopped = True
                        break

                    # Step 4: YOLO person detection
                    person = detect_person(img_path, yolo_model, self.person_confidence)
                    if person is None:
                        _passthrough(img_path)
                        passthrough_count += 1
                        continue

                    # Person bounding box with padding expansion = outer crop boundary
                    px1 = max(0,  int(person.center_x - person.width  / 2) - padding)
                    py1 = max(0,  int(person.center_y - person.height / 2) - padding)
                    px2 = min(iw, int(person.center_x + person.width  / 2) + padding)
                    py2 = min(ih, int(person.center_y + person.height / 2) + padding)

                    # Step 5: NudeNet focus (if body-part classes are selected)
                    if target_classes:
                        # --- STOP CHECK 3 (before slow NudeNet call) ---
                        if self._nudenet_stop_event.is_set():
                            stopped = True
                            break

                        results = detect_all_body_parts(img_path, target_classes)
                        if results:
                            # Union-merge all matched body-part boxes into focus region
                            fx1, fy1, fx2, fy2 = iw, ih, 0, 0
                            for det in results:
                                x1, y1, x2, y2 = box_to_coords(
                                    det["box"],
                                    context_scale=context_scale,
                                    img_width=iw, img_height=ih,
                                )
                                fx1 = min(fx1, x1);  fy1 = min(fy1, y1)
                                fx2 = max(fx2, x2);  fy2 = max(fy2, y2)
                        else:
                            # No body-part match → fall back to YOLO person box
                            fx1, fy1, fx2, fy2 = px1, py1, px2, py2
                    else:
                        # YOLO-only mode
                        fx1, fy1, fx2, fy2 = px1, py1, px2, py2

                    # Step 7: clamp focus region to person box (outer boundary) + image
                    fx1 = max(px1, max(0,  fx1))
                    fy1 = max(py1, max(0,  fy1))
                    fx2 = min(px2, min(iw, fx2))
                    fy2 = min(py2, min(ih, fy2))

                    # Step 8: validate crop dimensions
                    if (fx2 - fx1) < 64 or (fy2 - fy1) < 64:
                        _passthrough(img_path)
                        passthrough_count += 1
                        continue
                    if min_px > 0 and ((fx2 - fx1) < min_px or (fy2 - fy1) < min_px):
                        _passthrough(img_path)
                        passthrough_count += 1
                        continue

                    # Step 9: crop → letterbox resize → save
                    cropped = img.crop((fx1, fy1, fx2, fy2))
                    resized = resize_letterbox(cropped, bucket)
                    saved = save_cropped_image_flat(resized, output_dir, bucket, img_path.stem)
                    self.pipeline_manager.add_to_caption_queue(saved)
                    cropped_count += 1

                except Exception:
                    _passthrough(img_path)
                    passthrough_count += 1

            set_status("Ready")
            return cropped_count, passthrough_count, stopped

        def on_done(cropped_count, passthrough_count, stopped):
            if hasattr(self, '_btn_smart_stop'):
                self._btn_smart_stop.configure(state="disabled")
            status = "Stopped" if stopped else "Smart crop done"
            self.status_label.configure(
                text=f"{status}: {cropped_count} cropped, {passthrough_count} passthrough"
            )
            stop_note = "\n(Stopped early by user.)" if stopped else ""
            messagebox.showinfo(
                "Smart Crop Complete",
                f"{cropped_count} image(s) cropped and saved.\n"
                f"{passthrough_count} passed through (no person or too small).{stop_note}\n\n"
                "Switch to the Wizard tab to continue."
            )

        def on_error(e):
            from ui.app_main import set_status
            set_status("Ready")
            if hasattr(self, '_btn_smart_stop'):
                self._btn_smart_stop.configure(state="disabled")
            self.status_label.configure(text=f"Smart crop error: {e}")
            messagebox.showerror("Smart Crop Error", str(e))

        def run():
            try:
                result = work()
                self.after(0, lambda: on_done(*result))
            except Exception as e:
                self.after(0, lambda: on_error(e))

        threading.Thread(target=run, daemon=True).start()

    def run_smart_crop_stop(self):
        """Signal the running smart crop batch to stop after the current image."""
        self._nudenet_stop_event.set()
        if hasattr(self, '_btn_smart_stop'):
            self._btn_smart_stop.configure(state="disabled")

    # ------------------------------------------------------------------
    # Watermark scan
    # ------------------------------------------------------------------

    def run_watermark_scan(self):
        """Run WD14 tagger on all source images and auto-copy clean ones to output."""
        effective_output = self.output_folder or self.pipeline_manager.output_folder
        if not self.image_files:
            messagebox.showwarning("Warning", "No images loaded. Select a source folder first.")
            return
        if not effective_output:
            messagebox.showwarning("Warning", "Please select an output folder first.")
            return

        threshold = self.wm_threshold_var.get()
        files = list(self.image_files)
        total = len(files)
        self._wm_scan_btn.configure(state="disabled")

        def work():
            from ui.app_main import set_status, set_progress
            from core.ai.tagger import WD14Tagger
            set_status(f"Watermark scan — loading tagger…", busy=True)
            tagger = WD14Tagger()
            tagger.load_model()

            clean_paths = []
            watermarked_paths = []
            for i, img_path in enumerate(files):
                set_progress(i + 1, total, f"Scanning {i + 1}/{total}: {img_path.name}")
                tags = tagger.tag_image(img_path, threshold=threshold)
                if "watermark" in tags or "text" in tags:
                    watermarked_paths.append(img_path)
                else:
                    clean_paths.append(img_path)

            # Copy clean images to output with nocrop_ prefix so the stem
            # detector can identify them regardless of source file extension.
            copied = []
            for img_path in clean_paths:
                dest = Path(effective_output) / f"nocrop_{img_path.name}"
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(img_path, dest)
                    self.pipeline_manager.add_to_caption_queue(dest)
                    copied.append(img_path)
                except shutil.SameFileError:
                    copied.append(img_path)
                except Exception:
                    pass

            set_status("Ready")
            return copied, watermarked_paths

        def on_done(copied, watermarked):
            # Remove processed clean images from the list
            copied_set = set(copied)
            self.image_files = [f for f in self.image_files if f not in copied_set]
            self.current_index = min(self.current_index, max(0, len(self.image_files) - 1))
            n_clean = len(copied)
            n_wm = len(watermarked)
            self.status_label.configure(
                text=f"Scan done: {n_clean} clean → output, {n_wm} watermarked kept"
            )
            self._wm_scan_btn.configure(state="normal")
            if self.image_files:
                self.load_current_image()
            else:
                self.original_image = None
                self.canvas.delete("all")
            messagebox.showinfo(
                "Watermark scan complete",
                f"{n_clean} clean image(s) sent to output.\n"
                f"{n_wm} image(s) flagged as watermarked remain in the list."
            )

        def on_error(e):
            from ui.app_main import set_status
            set_status("Ready")
            self._wm_scan_btn.configure(state="normal")
            self.status_label.configure(text=f"Scan error: {e}")
            messagebox.showerror("Watermark scan error", str(e))

        def run():
            try:
                copied, watermarked = work()
                self.after(0, lambda: on_done(copied, watermarked))
            except Exception as e:
                self.after(0, lambda: on_error(e))

        threading.Thread(target=run, daemon=True).start()

    # ------------------------------------------------------------------
    # Body-part detection
    # ------------------------------------------------------------------

    def _get_selected_nudenet_classes(self) -> list:
        """Return the list of NudeNet class keys whose checkboxes are ticked."""
        return [cls for cls, var in self.body_part_vars.items() if var.get()]

    def run_body_part_detect_current(self):
        """Run NudeNet on the current image and set the crop box to the detected region."""
        if not self.image_files or self.current_index >= len(self.image_files):
            messagebox.showwarning("Warning", "No image loaded.")
            return
        if not self.original_image:
            messagebox.showwarning("Warning", "Image not loaded yet.")
            return

        target_classes = self._get_selected_nudenet_classes()
        if not target_classes:
            messagebox.showwarning("No selection",
                                   "Tick at least one body part in the list first.")
            return

        img_path = self.image_files[self.current_index]

        def work():
            from ui.app_main import set_status
            set_status("Detecting body part…", busy=True)
            try:
                result = detect_body_parts(img_path, target_classes)
            finally:
                set_status("Ready")
            return result

        def on_done(result):
            if result is None:
                messagebox.showinfo(
                    "Not detected",
                    "None of the selected body parts were found in this image "
                    "(score threshold: 0.4)."
                )
                return
            x1, y1, x2, y2 = box_to_coords(
                result["box"],
                context_scale=self.nudenet_context_scale.get(),
                img_width=self.original_image.width,
                img_height=self.original_image.height,
            )
            self.crop_x1, self.crop_y1 = x1, y1
            self.crop_x2, self.crop_y2 = x2, y2
            if self.current_bucket == "no_crop":
                self.current_bucket = "square"
                self.bucket_var.set("square")
            self.update_display()

        def on_error(e):
            messagebox.showerror("Detection error", str(e))

        def run():
            try:
                result = work()
                self.after(0, lambda: on_done(result))
            except Exception as e:
                self.after(0, lambda: on_error(e))

        threading.Thread(target=run, daemon=True).start()

