"""Event handlers for SortTab canvas interactions."""

from typing import Optional
from PIL import Image
from tkinter import Canvas

from ui.tabs.tab_sort_canvas import CanvasHelper
from ui.tabs.tab_sort_display import clamp_crop_to_bounds, clamp_resize_crop

MIN_CROP_SIZE = 64


def handle_canvas_click(event, canvas: Canvas, canvas_helper: Optional[CanvasHelper],
                       crop_x1: float, crop_y1: float, crop_x2: float, crop_y2: float) -> tuple[Optional[str], float, float]:
    """Handle canvas click: hit-test corner/edge handles or interior (move).
    
    Returns:
        (drag_mode, drag_start_x, drag_start_y) tuple
    """
    if not canvas_helper:
        return None, 0.0, 0.0
    
    canvas_x = canvas.canvasx(event.x)
    canvas_y = canvas.canvasy(event.y)
    img_x, img_y = canvas_helper.canvas_to_image_coords(canvas_x, canvas_y)
    
    drag_mode = canvas_helper.hit_test_handle(img_x, img_y, crop_x1, crop_y1, crop_x2, crop_y2)
    return drag_mode, img_x, img_y


def handle_canvas_drag(event, canvas: Canvas, canvas_helper: Optional[CanvasHelper],
                      original_image: Optional[Image.Image], drag_mode: Optional[str],
                      drag_start_x: float, drag_start_y: float,
                      crop_x1: float, crop_y1: float, crop_x2: float, crop_y2: float) -> tuple[float, float, float, float]:
    """Handle canvas drag: move or resize crop box.
    
    Returns:
        (crop_x1, crop_y1, crop_x2, crop_y2) updated coordinates
    """
    if not drag_mode or not original_image or not canvas_helper:
        return crop_x1, crop_y1, crop_x2, crop_y2
    
    canvas_x = canvas.canvasx(event.x)
    canvas_y = canvas.canvasy(event.y)
    img_x, img_y = canvas_helper.canvas_to_image_coords(canvas_x, canvas_y)
    img_width, img_height = original_image.size
    
    if drag_mode == "move":
        dx = img_x - drag_start_x
        dy = img_y - drag_start_y
        new_x1 = crop_x1 + dx
        new_y1 = crop_y1 + dy
        new_x2 = crop_x2 + dx
        new_y2 = crop_y2 + dy
        new_x1, new_y1, new_x2, new_y2 = clamp_crop_to_bounds(
            new_x1, new_y1, new_x2, new_y2, img_width, img_height
        )
        return new_x1, new_y1, new_x2, new_y2
    
    # Resize: move one or two edges depending on handle
    if drag_mode == "resize_nw":
        new_x1, new_y1, new_x2, new_y2 = img_x, img_y, crop_x2, crop_y2
    elif drag_mode == "resize_ne":
        new_x1, new_y1, new_x2, new_y2 = crop_x1, img_y, img_x, crop_y2
    elif drag_mode == "resize_sw":
        new_x1, new_y1, new_x2, new_y2 = img_x, crop_y1, crop_x2, img_y
    elif drag_mode == "resize_se":
        new_x1, new_y1, new_x2, new_y2 = crop_x1, crop_y1, img_x, img_y
    elif drag_mode == "resize_n":
        new_x1, new_y1, new_x2, new_y2 = crop_x1, img_y, crop_x2, crop_y2
    elif drag_mode == "resize_s":
        new_x1, new_y1, new_x2, new_y2 = crop_x1, crop_y1, crop_x2, img_y
    elif drag_mode == "resize_w":
        new_x1, new_y1, new_x2, new_y2 = img_x, crop_y1, crop_x2, crop_y2
    elif drag_mode == "resize_e":
        new_x1, new_y1, new_x2, new_y2 = crop_x1, crop_y1, img_x, crop_y2
    else:
        return crop_x1, crop_y1, crop_x2, crop_y2
    
    # Normalize so (x1,y1) is top-left and (x2,y2) is bottom-right, then clamp
    nx1 = min(new_x1, new_x2)
    nx2 = max(new_x1, new_x2)
    ny1 = min(new_y1, new_y2)
    ny2 = max(new_y1, new_y2)
    return clamp_resize_crop(nx1, ny1, nx2, ny2, img_width, img_height, MIN_CROP_SIZE)
