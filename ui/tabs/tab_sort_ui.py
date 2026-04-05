"""UI setup helpers for SortTab."""

import customtkinter as ctk
from tkinter import Canvas, Scrollbar
from core.config import BUCKETS
from typing import Dict, Callable
from ui.tooltip import add_tooltip


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
    """Create right control panel with bucket selection and actions.
    
    Returns:
        (right_panel, widgets_dict) tuple where widgets_dict contains label references
    """
    right_panel = ctk.CTkScrollableFrame(parent, width=300)
    right_panel.pack(side="right", fill="y")
    
    widgets = {}
    
    # Bucket selection
    bucket_frame = ctk.CTkFrame(right_panel)
    bucket_frame.pack(fill="x", padx=10, pady=10)
    ctk.CTkLabel(bucket_frame, text="Bucket Selection", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=5)
    
    bucket_var = ctk.StringVar(value="square")
    for bucket in ['portrait', 'square', 'landscape']:
        w, h = BUCKETS[bucket]
        rb = ctk.CTkRadioButton(bucket_frame, text=f"{bucket.title()} ({w}×{h})",
                                variable=bucket_var, value=bucket)
        rb.pack(anchor="w", padx=20, pady=2)
        add_tooltip(rb, f"Crop and resize the image to the {bucket} bucket ({w}×{h} px)")
    no_crop_rb = ctk.CTkRadioButton(
        bucket_frame,
        text="No crop  (pass through at original size)",
        variable=bucket_var,
        value="no_crop",
    )
    no_crop_rb.pack(anchor="w", padx=20, pady=(6, 2))
    add_tooltip(no_crop_rb, "Copy this image to the output folder at its original resolution without any crop or resize")
    widgets['bucket_var'] = bucket_var
    
    # Crop info
    info_frame = ctk.CTkFrame(right_panel)
    info_frame.pack(fill="x", padx=10, pady=10)
    crop_size_label = ctk.CTkLabel(info_frame, text="Crop: 0x0")
    crop_size_label.pack()
    widgets['crop_size_label'] = crop_size_label
    
    # Actions
    action_frame = ctk.CTkFrame(right_panel)
    action_frame.pack(fill="x", padx=10, pady=10)
    widgets['prev_button'] = ctk.CTkButton(action_frame, text="← Previous")
    widgets['prev_button'].pack(pady=5, fill="x")
    add_tooltip(widgets['prev_button'], "Go back to the previous image (does not undo saved crops)")
    widgets['save_button'] = ctk.CTkButton(action_frame, text="Save & Next", fg_color="green")
    widgets['save_button'].pack(pady=5, fill="x")
    add_tooltip(widgets['save_button'], "Crop and resize this image to the selected bucket, then advance to the next")
    widgets['skip_button'] = ctk.CTkButton(action_frame, text="Skip", fg_color="red")
    widgets['skip_button'].pack(pady=5, fill="x")
    add_tooltip(widgets['skip_button'], "Skip this image without saving a crop")
    widgets['auto_crop_button'] = ctk.CTkButton(action_frame, text="Auto crop all", fg_color="#1f538d")
    widgets['auto_crop_button'].pack(pady=5, fill="x")
    add_tooltip(widgets['auto_crop_button'], "Batch-crop all images in the source folder using YOLO person detection")
    
    return right_panel, widgets


def create_top_controls(parent, on_select_source: Callable, on_select_output: Callable, 
                       on_quality_filter: Callable) -> Dict:
    """Create top control frame with folder selection and quality filter controls.
    
    Returns:
        Dictionary with widget references (threshold vars, status label, etc.)
    """
    control_frame = ctk.CTkFrame(parent)
    control_frame.pack(fill="x", padx=10, pady=10)
    
    widgets = {}
    
    # Folder selection
    _src_btn = ctk.CTkButton(control_frame, text="Select Source", command=on_select_source)
    _src_btn.pack(side="left", padx=5)
    add_tooltip(_src_btn, "Choose the folder containing images to crop")
    _out_btn = ctk.CTkButton(control_frame, text="Select Output", command=on_select_output)
    _out_btn.pack(side="left", padx=5)
    add_tooltip(_out_btn, "Choose the folder where cropped images will be saved")
    _qf_btn = ctk.CTkButton(control_frame, text="Quality Filter", command=on_quality_filter)
    _qf_btn.pack(side="left", padx=5)
    add_tooltip(_qf_btn, "Run blur and aesthetic scoring and move rejects to a subfolder")
    
    # Threshold sliders with labels
    blur_threshold_var = ctk.DoubleVar(value=100.0)
    ctk.CTkLabel(control_frame, text="Blur (Laplacian):").pack(side="left", padx=(10, 2))
    _blur_slider = ctk.CTkSlider(control_frame, from_=0, to=500, variable=blur_threshold_var, width=100)
    _blur_slider.pack(side="left", padx=2)
    add_tooltip(_blur_slider, "Laplacian variance threshold — images below this value are considered blurry")
    widgets['blur_threshold_var'] = blur_threshold_var
    
    aesthetic_threshold_var = ctk.DoubleVar(value=5.0)
    ctk.CTkLabel(control_frame, text="Aesthetic (1-10):").pack(side="left", padx=(10, 2))
    _aes_slider = ctk.CTkSlider(control_frame, from_=1, to=10, variable=aesthetic_threshold_var, width=100)
    _aes_slider.pack(side="left", padx=2)
    add_tooltip(_aes_slider, "Aesthetic score threshold (1–10) — images below this score are considered low quality")
    widgets['aesthetic_threshold_var'] = aesthetic_threshold_var
    
    dry_run_var = ctk.BooleanVar(value=False)
    _dry_check = ctk.CTkCheckBox(control_frame, text="Dry Run", variable=dry_run_var)
    _dry_check.pack(side="left", padx=5)
    add_tooltip(_dry_check, "Preview which images would be rejected without actually moving any files")
    widgets['dry_run_var'] = dry_run_var
    
    status_label = ctk.CTkLabel(control_frame, text="Select folders to begin")
    status_label.pack(side="left", padx=20)
    widgets['status_label'] = status_label
    
    return control_frame, widgets


def select_folder_dialog(title: str) -> str:
    """Show folder selection dialog.
    
    Returns:
        Selected folder path or empty string
    """
    from tkinter import filedialog
    return filedialog.askdirectory(title=title) or ""
