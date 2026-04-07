"""UI setup helpers for SortTab."""

import customtkinter as ctk
from tkinter import Canvas, Scrollbar
from core.config import BUCKETS
from typing import Dict, Callable
from ui.tooltip import add_tooltip
from core.ai.nudenet_detector import DISPLAY_NAMES as _NUDENET_DISPLAY_NAMES


def create_canvas_frame(parent) -> tuple[Canvas, ctk.CTkFrame]:
    """Create canvas with scrollbars.
    
    Returns:
        (canvas, canvas_frame) tuple
    """
    canvas_frame = ctk.CTkFrame(parent)
    canvas_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
    
    v_scroll = Scrollbar(canvas_frame, orient="vertical")
    h_scroll = Scrollbar(canvas_frame, orient="horizontal")
    canvas = Canvas(canvas_frame, bg="#1a1a1a", yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
    v_scroll.config(command=canvas.yview)
    h_scroll.config(command=canvas.xview)
    
    canvas.grid(row=0, column=0, sticky="nsew")
    v_scroll.grid(row=0, column=1, sticky="ns")
    h_scroll.grid(row=1, column=0, sticky="ew")
    canvas_frame.grid_rowconfigure(0, weight=1)
    canvas_frame.grid_columnconfigure(0, weight=1)
    
    return canvas, canvas_frame


def create_control_panel(parent) -> tuple[ctk.CTkScrollableFrame, dict]:
    """Create right control panel.

    Sections follow the recommended workflow order:
      1. Session resume
      2. Batch tools  (reduce the queue automatically)
      3. Per-image review  (manually review what remains)
    
    Returns:
        (right_panel, widgets_dict) tuple where widgets_dict contains label references
    """
    right_panel = ctk.CTkScrollableFrame(parent, width=300)
    right_panel.pack(side="right", fill="y")

    widgets = {}

    # ── 1. Session resume ─────────────────────────────────────────────────────
    resume_frame = ctk.CTkFrame(right_panel)
    resume_frame.pack(fill="x", padx=10, pady=(10, 4))
    skip_done_var = ctk.BooleanVar(value=True)
    skip_done_cb = ctk.CTkCheckBox(resume_frame, text="Skip already cropped",
                                   variable=skip_done_var)
    skip_done_cb.pack(anchor="w", padx=10, pady=6)
    add_tooltip(skip_done_cb,
                "Hide source images that already have a matching file in the output "
                "folder so you can resume a previous session without re-cropping.")
    widgets['skip_done_var'] = skip_done_var

    # ── 2. Batch tools ────────────────────────────────────────────────────────
    batch_frame = ctk.CTkFrame(right_panel)
    batch_frame.pack(fill="x", padx=10, pady=(0, 4))
    ctk.CTkLabel(batch_frame, text="Batch Tools",
                 font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(8, 4))

    # -- Watermark scan --
    wm_row = ctk.CTkFrame(batch_frame, fg_color="transparent")
    wm_row.pack(fill="x", padx=10, pady=(0, 4))
    wm_threshold_var = ctk.DoubleVar(value=0.35)
    wm_label_row = ctk.CTkFrame(wm_row, fg_color="transparent")
    wm_label_row.pack(fill="x")
    ctk.CTkLabel(wm_label_row, text="Watermark threshold:").pack(side="left")
    wm_value_label = ctk.CTkLabel(wm_label_row, text="0.35", width=36, anchor="e")
    wm_value_label.pack(side="right")
    wm_slider = ctk.CTkSlider(wm_row, from_=0.1, to=0.9, variable=wm_threshold_var, width=150,
                              command=lambda v: wm_value_label.configure(text=f"{v:.2f}"))
    wm_slider.pack(anchor="w", pady=(2, 4))
    add_tooltip(wm_slider,
                "Confidence threshold for the WD14 'watermark' tag. "
                "Lower = more aggressive (flags more images as watermarked).")
    wm_btn = ctk.CTkButton(wm_row, text="Scan & passthrough clean", height=28)
    wm_btn.pack(fill="x", pady=(0, 6))
    add_tooltip(wm_btn,
                "Run the WD14 tagger on all source images. "
                "Images with no watermark tag above the threshold are "
                "automatically copied to the output folder.")
    widgets['wm_threshold_var'] = wm_threshold_var
    widgets['wm_scan_btn'] = wm_btn

    # -- Body-part batch detection (checkbox list) --
    # Wrapped in nudenet_section so it can be hidden when NudeNet is disabled in settings.
    nudenet_section = ctk.CTkFrame(batch_frame, fg_color="transparent")
    nudenet_section.pack(fill="x", padx=10, pady=(0, 4))
    bp_row = nudenet_section

    # Context padding slider — controls how much surrounding area is included
    ctx_header = ctk.CTkFrame(bp_row, fg_color="transparent")
    ctx_header.pack(fill="x", pady=(0, 2))
    ctk.CTkLabel(ctx_header, text="Context padding:").pack(side="left")
    nudenet_context_scale_var = ctk.DoubleVar(value=2.0)
    ctx_value_label = ctk.CTkLabel(ctx_header, text="2.00×", width=42, anchor="e")
    ctx_value_label.pack(side="right")
    ctx_slider = ctk.CTkSlider(
        bp_row, from_=1.0, to=4.0, variable=nudenet_context_scale_var, width=150,
        command=lambda v: ctx_value_label.configure(text=f"{float(v):.2f}×"),
    )
    ctx_slider.pack(anchor="w", pady=(0, 6))
    add_tooltip(ctx_slider,
                "How much surrounding area to include around the detected body part.\n"
                "1.0× = tight crop to the bounding box only.\n"
                "2.0× = double the box size (recommended).\n"
                "4.0× = very loose — includes most of the figure.")
    widgets['nudenet_context_scale_var'] = nudenet_context_scale_var

    ctk.CTkLabel(bp_row, text="Body parts to detect:").pack(anchor="w")
    bp_list_frame = ctk.CTkScrollableFrame(bp_row, height=140)
    bp_list_frame.pack(fill="x", pady=(2, 4))
    body_part_vars: dict = {}
    for class_key, display_label in _NUDENET_DISPLAY_NAMES.items():
        var = ctk.BooleanVar(value=False)
        cb = ctk.CTkCheckBox(bp_list_frame, text=display_label, variable=var)
        cb.pack(anchor="w", padx=4, pady=1)
        add_tooltip(cb, f"Include '{display_label}' in the detection scan")
        body_part_vars[class_key] = var
    widgets['body_part_vars'] = body_part_vars
    widgets['nudenet_section'] = nudenet_section

    # -- YOLO crop margin --
    yolo_row = ctk.CTkFrame(batch_frame, fg_color="transparent")
    yolo_row.pack(fill="x", padx=10, pady=(0, 4))
    yolo_hdr = ctk.CTkFrame(yolo_row, fg_color="transparent")
    yolo_hdr.pack(fill="x")
    ctk.CTkLabel(yolo_hdr, text="YOLO crop margin:").pack(side="left")
    yolo_margin_var = ctk.DoubleVar(value=50)
    yolo_value_label = ctk.CTkLabel(yolo_hdr, text="50 px", width=48, anchor="e")
    yolo_value_label.pack(side="right")
    yolo_slider = ctk.CTkSlider(
        yolo_row, from_=0, to=400, variable=yolo_margin_var, width=150,
        command=lambda v: yolo_value_label.configure(text=f"{int(v)} px"),
    )
    yolo_slider.pack(anchor="w", pady=(2, 4))
    add_tooltip(yolo_slider,
                "Controls how much context surrounds the detected person.\n"
                "0 px  = widest crop (maximum context / full frame).\n"
                "400 px = tightest crop (zoomed in on the person).\n"
                "Adjust here and the preview updates instantly before running the batch.")
    widgets['yolo_margin_var'] = yolo_margin_var

    # -- Minimum crop size --
    min_px_row = ctk.CTkFrame(batch_frame, fg_color="transparent")
    min_px_row.pack(fill="x", padx=10, pady=(0, 4))
    min_px_hdr = ctk.CTkFrame(min_px_row, fg_color="transparent")
    min_px_hdr.pack(fill="x")
    ctk.CTkLabel(min_px_hdr, text="Min. crop size:").pack(side="left")
    min_crop_px_var = ctk.IntVar(value=512)
    min_px_value_label = ctk.CTkLabel(min_px_hdr, text="512 px", width=52, anchor="e")
    min_px_value_label.pack(side="right")
    min_px_slider = ctk.CTkSlider(
        min_px_row, from_=0, to=1024, variable=min_crop_px_var, width=150,
        command=lambda v: min_px_value_label.configure(text=f"{int(v)} px"),
    )
    min_px_slider.pack(anchor="w", pady=(2, 4))
    add_tooltip(min_px_slider,
                "Images smaller than this size (either dimension) are passed through\n"
                "without cropping — they are likely already closely cropped.\n"
                "0 = disabled (all images are processed).")
    widgets['min_crop_px_var'] = min_crop_px_var

    # -- Smart Crop All (YOLO + optional NudeNet focus) --
    smart_btn_row = ctk.CTkFrame(batch_frame, fg_color="transparent")
    smart_btn_row.pack(fill="x", padx=10, pady=(0, 10))
    smart_crop_btn = ctk.CTkButton(smart_btn_row, text="Smart Crop All", height=28,
                                   fg_color="#1f538d")
    smart_crop_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))
    add_tooltip(smart_crop_btn,
                "Batch-process every image in the source folder:\n"
                "  1. YOLO detects person → sets outer crop boundary.\n"
                "  2. If body parts are checked, NudeNet focuses the crop on those regions.\n"
                "  3. No person found → image is passed through as nocrop_.\n"
                "  4. Result too small → image is passed through as nocrop_.")
    smart_stop_btn = ctk.CTkButton(smart_btn_row, text="Stop", height=28, width=60,
                                   fg_color="gray40", state="disabled")
    smart_stop_btn.pack(side="left")
    add_tooltip(smart_stop_btn, "Stop the Smart Crop batch after the current image finishes.")
    widgets['smart_crop_btn'] = smart_crop_btn
    widgets['smart_stop_btn'] = smart_stop_btn

    # ── 3. Per-image review ───────────────────────────────────────────────────
    review_frame = ctk.CTkFrame(right_panel)
    review_frame.pack(fill="x", padx=10, pady=(0, 4))
    ctk.CTkLabel(review_frame, text="Per-Image Review",
                 font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(8, 4))

    # Single-image NudeNet detect — part of nudenet_section_review (hidden when NudeNet is off)
    nudenet_section_review = ctk.CTkFrame(review_frame, fg_color="transparent")
    nudenet_section_review.pack(fill="x", padx=10, pady=(0, 4))
    bp_detect_btn = ctk.CTkButton(nudenet_section_review, text="Detect body part on this image",
                                  height=28)
    bp_detect_btn.pack(fill="x", pady=(0, 4))
    add_tooltip(bp_detect_btn,
                "Run NudeNet on the current image using the checked body parts above. "
                "The crop box is set to the highest-confidence match — adjust and save normally.")
    widgets['bp_detect_btn'] = bp_detect_btn
    widgets['nudenet_section_review'] = nudenet_section_review

    # Bucket selection
    bucket_frame = ctk.CTkFrame(review_frame)
    bucket_frame.pack(fill="x", padx=10, pady=(0, 4))
    ctk.CTkLabel(bucket_frame, text="Crop bucket",
                 font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=4, pady=(4, 2))
    bucket_var = ctk.StringVar(value="square")
    for bucket in ['portrait', 'square', 'landscape']:
        w, h = BUCKETS[bucket]
        rb = ctk.CTkRadioButton(bucket_frame, text=f"{bucket.title()} ({w}×{h})",
                                variable=bucket_var, value=bucket)
        rb.pack(anchor="w", padx=16, pady=2)
        add_tooltip(rb, f"Crop and resize the image to the {bucket} bucket ({w}×{h} px)")
    no_crop_rb = ctk.CTkRadioButton(
        bucket_frame,
        text="No crop  (pass through at original size)",
        variable=bucket_var,
        value="no_crop",
    )
    no_crop_rb.pack(anchor="w", padx=16, pady=(6, 4))
    add_tooltip(no_crop_rb,
                "Copy this image to the output folder at its original resolution without any crop or resize")
    widgets['bucket_var'] = bucket_var

    # Crop size info
    crop_size_label = ctk.CTkLabel(review_frame, text="Crop: —")
    crop_size_label.pack(pady=(2, 4))
    widgets['crop_size_label'] = crop_size_label

    # Per-image action buttons
    action_frame = ctk.CTkFrame(review_frame, fg_color="transparent")
    action_frame.pack(fill="x", padx=10, pady=(0, 10))
    widgets['prev_button'] = ctk.CTkButton(action_frame, text="← Previous")
    widgets['prev_button'].pack(pady=3, fill="x")
    add_tooltip(widgets['prev_button'], "Go back to the previous image (does not undo saved crops)")
    widgets['save_button'] = ctk.CTkButton(action_frame, text="Save & Next", fg_color="green")
    widgets['save_button'].pack(pady=3, fill="x")
    add_tooltip(widgets['save_button'],
                "Crop and resize this image to the selected bucket, then advance to the next")
    widgets['skip_button'] = ctk.CTkButton(action_frame, text="Skip", fg_color="red")
    widgets['skip_button'].pack(pady=3, fill="x")
    add_tooltip(widgets['skip_button'], "Skip this image without saving a crop")

    return right_panel, widgets


def create_top_controls(parent, on_select_source: Callable, on_select_output: Callable,
                        on_quality_filter: Callable) -> Dict:
    """Create top control frame with folder selection and quality filter controls.

    Split into two rows so all controls are visible at any reasonable window width.

    Returns:
        Dictionary with widget references (threshold vars, status label, etc.)
    """
    control_frame = ctk.CTkFrame(parent)
    control_frame.pack(fill="x", padx=10, pady=(10, 4))

    widgets = {}

    # Row 1 — folder buttons
    row1 = ctk.CTkFrame(control_frame, fg_color="transparent")
    row1.pack(fill="x", padx=4, pady=(4, 0))
    _src_btn = ctk.CTkButton(row1, text="Select Source", width=120, command=on_select_source)
    _src_btn.pack(side="left", padx=(0, 6))
    add_tooltip(_src_btn, "Choose the folder containing images to crop")
    _out_btn = ctk.CTkButton(row1, text="Select Output", width=120, command=on_select_output)
    _out_btn.pack(side="left", padx=(0, 6))
    add_tooltip(_out_btn, "Choose the folder where cropped images will be saved")
    _qf_btn = ctk.CTkButton(row1, text="Quality Filter", width=120, command=on_quality_filter)
    _qf_btn.pack(side="left", padx=(0, 6))
    add_tooltip(_qf_btn, "Run blur and aesthetic scoring and move rejects to a subfolder")

    # Row 2 — quality filter thresholds + dry run + status
    row2 = ctk.CTkFrame(control_frame, fg_color="transparent")
    row2.pack(fill="x", padx=4, pady=(4, 4))

    blur_threshold_var = ctk.DoubleVar(value=100.0)
    ctk.CTkLabel(row2, text="Blur:").pack(side="left", padx=(0, 2))
    _blur_slider = ctk.CTkSlider(row2, from_=0, to=500, variable=blur_threshold_var, width=90)
    _blur_slider.pack(side="left", padx=(0, 8))
    add_tooltip(_blur_slider, "Laplacian variance threshold — images below this value are considered blurry")
    widgets['blur_threshold_var'] = blur_threshold_var

    aesthetic_threshold_var = ctk.DoubleVar(value=5.0)
    ctk.CTkLabel(row2, text="Aesthetic (1-10):").pack(side="left", padx=(0, 2))
    _aes_slider = ctk.CTkSlider(row2, from_=1, to=10, variable=aesthetic_threshold_var, width=90)
    _aes_slider.pack(side="left", padx=(0, 8))
    add_tooltip(_aes_slider, "Aesthetic score threshold (1–10) — images below this score are considered low quality")
    widgets['aesthetic_threshold_var'] = aesthetic_threshold_var

    dry_run_var = ctk.BooleanVar(value=False)
    _dry_check = ctk.CTkCheckBox(row2, text="Dry Run", variable=dry_run_var)
    _dry_check.pack(side="left", padx=5)
    add_tooltip(_dry_check, "Preview which images would be rejected without actually moving any files")
    widgets['dry_run_var'] = dry_run_var
    
    status_label = ctk.CTkLabel(row2, text="Select folders to begin")
    status_label.pack(side="left", padx=(12, 4))
    widgets['status_label'] = status_label
    
    return control_frame, widgets


def select_folder_dialog(title: str) -> str:
    """Show folder selection dialog.
    
    Returns:
        Selected folder path or empty string
    """
    from tkinter import filedialog
    return filedialog.askdirectory(title=title) or ""
