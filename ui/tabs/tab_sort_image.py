"""Image loading and processing helpers for SortTab."""

from pathlib import Path
from typing import Optional, Tuple
from PIL import Image

from core.ai.cropper import detect_person, calculate_crop_box, auto_select_bucket, detect_bucket_from_dimensions
from core.ai.vram import get_vram_manager


def load_and_process_image(
    image_path: Path,
    vram_manager,
    person_confidence: float,
    padding_margin: int,
    current_bucket: str,
    auto_bucket_enabled: bool = False,
) -> Tuple[Image.Image, Optional[object], str, Tuple[int, int, int, int]]:
    """Load image and perform person detection and crop calculation.
    
    Args:
        image_path: Path to image file
        vram_manager: VRAMManager instance
        person_confidence: Person detection confidence threshold
        padding_margin: Padding margin for crop
        current_bucket: Current bucket selection
    
    Returns:
        (image, person, selected_bucket, crop_coords) tuple
    """
    # Load image — call .load() immediately so PIL releases the OS file handle.
    # Without this, Windows raises WinError 32 when save_and_next tries to
    # copy the same file with shutil.copy2 while PIL still holds it open.
    image = Image.open(image_path)
    image.load()

    # Detect person and pick bucket.
    # Baseline: classify by the image's own aspect ratio so portrait/landscape
    # images are never wrongly pre-selected as square.
    yolo_model = vram_manager.load_yolo()
    person = detect_person(image_path, yolo_model, person_confidence)
    selected_bucket = detect_bucket_from_dimensions(image.width, image.height)

    # YOLO override: if auto_bucket is on and a person was found, use the
    # person's aspect ratio (more accurate for subject-centred crops).
    if auto_bucket_enabled and person is not None:
        selected_bucket = auto_select_bucket(person.aspect_ratio)

    # Manual override: only honour current_bucket if it is the explicit
    # no_crop selection — everything else uses dimension/YOLO detection.
    if current_bucket == "no_crop":
        selected_bucket = "no_crop"

    # Guard: calculate_crop_box has no "no_crop" entry in BUCKETS, so skip it.
    if selected_bucket == "no_crop":
        crop_coords = (0, 0, image.width, image.height)
    else:
        crop_coords = calculate_crop_box(image, person, selected_bucket, padding_margin)

    return image, person, selected_bucket, crop_coords
