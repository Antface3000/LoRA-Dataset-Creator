"""Display update helpers for SortTab."""

from PIL import Image, ImageTk, ImageDraw
from typing import Optional


def create_crop_overlay(
    original_image: Image.Image,
    crop_x1: float,
    crop_y1: float,
    crop_x2: float,
    crop_y2: float,
    canvas_width: int,
    canvas_height: int
) -> ImageTk.PhotoImage:
    """Create display image with crop overlay.
    
    Args:
        original_image: Original PIL Image
        crop_x1, crop_y1, crop_x2, crop_y2: Crop coordinates
        canvas_width, canvas_height: Canvas dimensions
    
    Returns:
        PhotoImage ready for display
    """
    # Calculate scale
    scale = min(canvas_width / original_image.width, canvas_height / original_image.height, 1.0)
    
    display_size = (int(original_image.width * scale), int(original_image.height * scale))
    display_image = original_image.resize(display_size, Image.Resampling.LANCZOS)
    
    # Draw crop overlay
    overlay = display_image.copy().convert("RGBA")
    draw = ImageDraw.Draw(overlay)
    
    crop_x1_d = crop_x1 * scale
    crop_y1_d = crop_y1 * scale
    crop_x2_d = crop_x2 * scale
    crop_y2_d = crop_y2 * scale
    
    # Darken outside crop
    dark = Image.new('RGBA', overlay.size, (0, 0, 0, 128))
    overlay = Image.alpha_composite(overlay, dark)
    draw = ImageDraw.Draw(overlay)
    
    # Draw crop rectangle
    draw.rectangle([crop_x1_d, crop_y1_d, crop_x2_d, crop_y2_d], outline="yellow", width=3)
    
    # Draw corner and edge handles (small squares)
    handle_r = 6
    corners = [
        (crop_x1_d, crop_y1_d), (crop_x2_d, crop_y1_d),
        (crop_x1_d, crop_y2_d), (crop_x2_d, crop_y2_d)
    ]
    for cx, cy in corners:
        draw.rectangle(
            [cx - handle_r, cy - handle_r, cx + handle_r, cy + handle_r],
            outline="white", fill="yellow", width=2
        )
    mid_n = ((crop_x1_d + crop_x2_d) / 2, crop_y1_d)
    mid_s = ((crop_x1_d + crop_x2_d) / 2, crop_y2_d)
    mid_w = (crop_x1_d, (crop_y1_d + crop_y2_d) / 2)
    mid_e = (crop_x2_d, (crop_y1_d + crop_y2_d) / 2)
    for cx, cy in [mid_n, mid_s, mid_w, mid_e]:
        draw.rectangle(
            [cx - handle_r, cy - handle_r, cx + handle_r, cy + handle_r],
            outline="white", fill="yellow", width=2
        )
    
    return ImageTk.PhotoImage(overlay.convert("RGB"))


def clamp_crop_to_bounds(
    crop_x1: float, crop_y1: float, crop_x2: float, crop_y2: float,
    img_width: int, img_height: int
) -> tuple[float, float, float, float]:
    """Clamp crop box to image boundaries (preserves size).
    
    Returns:
        (crop_x1, crop_y1, crop_x2, crop_y2) clamped coordinates
    """
    crop_width = crop_x2 - crop_x1
    crop_height = crop_y2 - crop_y1
    new_x1 = crop_x1
    new_y1 = crop_y1
    new_x2 = crop_x2
    new_y2 = crop_y2
    if new_x1 < 0:
        new_x1 = 0
        new_x2 = crop_width
    elif new_x2 > img_width:
        new_x2 = img_width
        new_x1 = img_width - crop_width
    if new_y1 < 0:
        new_y1 = 0
        new_y2 = crop_height
    elif new_y2 > img_height:
        new_y2 = img_height
        new_y1 = img_height - crop_height
    return new_x1, new_y1, new_x2, new_y2


def clamp_resize_crop(
    crop_x1: float, crop_y1: float, crop_x2: float, crop_y2: float,
    img_width: int, img_height: int, min_size: int
) -> tuple[float, float, float, float]:
    """Clamp resize crop to image bounds and enforce minimum size.
    
    Returns:
        (crop_x1, crop_y1, crop_x2, crop_y2) clamped coordinates
    """
    w = crop_x2 - crop_x1
    h = crop_y2 - crop_y1
    if w < min_size:
        w = min_size
    if h < min_size:
        h = min_size
    new_x1 = max(0, min(crop_x1, img_width - w))
    new_y1 = max(0, min(crop_y1, img_height - h))
    new_x2 = new_x1 + w
    new_y2 = new_y1 + h
    if new_x2 > img_width:
        new_x2 = img_width
        new_x1 = img_width - w
    if new_y2 > img_height:
        new_y2 = img_height
        new_y1 = img_height - h
    return new_x1, new_y1, new_x2, new_y2
