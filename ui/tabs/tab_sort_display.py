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
    
    # Darken only the four strips OUTSIDE the crop box.
    # Build a fully-transparent layer, paint the outside regions dark, then
    # composite it — the crop area stays at full brightness.
    mask = Image.new('RGBA', overlay.size, (0, 0, 0, 0))
    mask_draw = ImageDraw.Draw(mask)
    shadow = (0, 0, 0, 140)
    w, h = overlay.size
    # top strip
    if crop_y1_d > 0:
        mask_draw.rectangle([0, 0, w, crop_y1_d], fill=shadow)
    # bottom strip
    if crop_y2_d < h:
        mask_draw.rectangle([0, crop_y2_d, w, h], fill=shadow)
    # left strip (middle band)
    if crop_x1_d > 0:
        mask_draw.rectangle([0, crop_y1_d, crop_x1_d, crop_y2_d], fill=shadow)
    # right strip (middle band)
    if crop_x2_d < w:
        mask_draw.rectangle([crop_x2_d, crop_y1_d, w, crop_y2_d], fill=shadow)
    overlay = Image.alpha_composite(overlay, mask)
    draw = ImageDraw.Draw(overlay)

    # Draw crop rectangle border
    draw.rectangle([crop_x1_d, crop_y1_d, crop_x2_d, crop_y2_d], outline="yellow", width=3)
    
    # Draw corner and edge handles (small squares).
    # Clamp each handle centre so it is never closer than handle_r pixels to
    # the image boundary — this prevents handles from being half-clipped when
    # the crop box is flush with the top, bottom, left, or right edge.
    handle_r = 6
    ow, oh = overlay.size

    def _ch(cx, cy):
        """Clamp handle centre to stay fully inside the image."""
        return max(handle_r, min(ow - handle_r, cx)), max(handle_r, min(oh - handle_r, cy))

    corners = [
        (crop_x1_d, crop_y1_d), (crop_x2_d, crop_y1_d),
        (crop_x1_d, crop_y2_d), (crop_x2_d, crop_y2_d)
    ]
    for raw_cx, raw_cy in corners:
        cx, cy = _ch(raw_cx, raw_cy)
        draw.rectangle(
            [cx - handle_r, cy - handle_r, cx + handle_r, cy + handle_r],
            outline="white", fill="yellow", width=2
        )
    mid_n = ((crop_x1_d + crop_x2_d) / 2, crop_y1_d)
    mid_s = ((crop_x1_d + crop_x2_d) / 2, crop_y2_d)
    mid_w = (crop_x1_d, (crop_y1_d + crop_y2_d) / 2)
    mid_e = (crop_x2_d, (crop_y1_d + crop_y2_d) / 2)
    for raw_cx, raw_cy in [mid_n, mid_s, mid_w, mid_e]:
        cx, cy = _ch(raw_cx, raw_cy)
        draw.rectangle(
            [cx - handle_r, cy - handle_r, cx + handle_r, cy + handle_r],
            outline="white", fill="yellow", width=2
        )
    
    return ImageTk.PhotoImage(overlay.convert("RGB"))


def create_plain_display(
    original_image: Image.Image,
    canvas_width: int,
    canvas_height: int,
) -> ImageTk.PhotoImage:
    """Create a display image scaled to fit the canvas with no crop overlay.

    Used when the 'No crop (pass through)' bucket is active.
    """
    scale = min(canvas_width / original_image.width, canvas_height / original_image.height, 1.0)
    display_size = (int(original_image.width * scale), int(original_image.height * scale))
    display_image = original_image.resize(display_size, Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(display_image.convert("RGB"))


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
