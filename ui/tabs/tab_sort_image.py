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
    # Load image
    image = Image.open(image_path)
    
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

    # Manual override: if the user has already picked a non-default bucket
    # for this session (current_bucket was set by the user, not auto), keep it.
    # We detect "manual" by checking if current_bucket differs from what
    # dimension-detection would choose — the radio button trace will have
    # already updated current_bucket before this call on bucket-change events,
    # but on initial load current_bucket is still the previous image's bucket
    # (or the default 'square'), so we prefer the dimension-based result there.
    # Rule: only honour current_bucket if it matches no_crop (explicit skip).
    if current_bucket == "no_crop":
        selected_bucket = "no_crop"
    
    # Calculate initial crop for selected bucket (person still used for center if detected)
    crop_coords = calculate_crop_box(image, person, selected_bucket, padding_margin)
    
    return image, person, selected_bucket, crop_coords
