"""Image loading and processing helpers for SortTab."""

from pathlib import Path
from typing import Optional, Tuple
from PIL import Image

from core.ai.cropper import detect_person, calculate_crop_box, auto_select_bucket
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
    
    # Detect person and optionally pick bucket automatically.
    yolo_model = vram_manager.load_yolo()
    person = detect_person(image_path, yolo_model, person_confidence)
    if auto_bucket_enabled:
        selected_bucket = auto_select_bucket(person.aspect_ratio if person else None)
    else:
        selected_bucket = current_bucket
    
    # Calculate initial crop for selected bucket (person still used for center if detected)
    crop_coords = calculate_crop_box(image, person, selected_bucket, padding_margin)
    
    return image, person, selected_bucket, crop_coords
