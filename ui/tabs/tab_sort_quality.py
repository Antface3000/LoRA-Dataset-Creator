"""Quality filter batch processing for SortTab."""

from pathlib import Path
from typing import List
import customtkinter as ctk
from tkinter import messagebox

from core.pipeline_manager import get_pipeline_manager
from core.data.file_handler import load_image_files, move_to_rejects, create_reject_folders


def run_quality_filter_batch(
    source_folder: Path,
    pipeline_manager,
    blur_threshold: float,
    aesthetic_threshold: float,
    dry_run: bool,
    mode: str = "aesthetic",
    status_callback=None
) -> tuple[int, int]:
    """Run quality filter on all images in source folder.
    
    Args:
        source_folder: Source directory path
        pipeline_manager: PipelineManager instance
        blur_threshold: Laplacian variance threshold
        aesthetic_threshold: Aesthetic score threshold
        dry_run: If True, don't move files
        mode: "blur" or "aesthetic"
        status_callback: Optional callback(status_text) for progress updates
    
    Returns:
        (passed_count, rejected_count) tuple
    """
    # Get all image files
    image_files = load_image_files(source_folder)
    if not image_files:
        return 0, 0
    
    # Create reject folders if not dry run
    if not dry_run:
        create_reject_folders(source_folder)
    rejects_dir = source_folder / "rejects"
    
    passed_count = 0
    rejected_count = 0
    
    for i, image_path in enumerate(image_files):
        if status_callback:
            status_callback(f"Filtering {i+1}/{len(image_files)}: {image_path.name}...")
        
        passed, score, new_path = pipeline_manager.process_stage1_quality_gate(
            image_path,
            mode=mode,
            blur_threshold=blur_threshold,
            aesthetic_threshold=aesthetic_threshold,
            rename_with_score=(mode == "aesthetic")
        )
        
        if dry_run:
            status = "Would Keep" if passed else "Would Reject"
            print(f"[DRY RUN] {image_path.name}: Score {score:.2f} ({status})")
            if passed:
                passed_count += 1
            else:
                rejected_count += 1
        else:
            if not passed:
                move_to_rejects(image_path, rejects_dir)
                rejected_count += 1
            else:
                passed_count += 1
    
    return passed_count, rejected_count
