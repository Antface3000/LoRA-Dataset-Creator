"""Event handlers for SortTab canvas interactions."""

from typing import Literal, Optional, Tuple

from PIL import Image
from tkinter import Canvas

from ui.tabs.tab_sort_canvas import CanvasHelper
from ui.tabs.tab_sort_display import clamp_crop_to_bounds

MIN_CROP_SIZE = 64

Interaction = Literal["resize", "move"]


def _normalize_rect(
    x1: float, y1: float, x2: float, y2: float
) -> Tuple[float, float, float, float]:
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


def _clamp_inside_image(
    x1: float, y1: float, x2: float, y2: float, iw: int, ih: int
) -> Tuple[float, float, float, float]:
    w = max(1.0, x2 - x1)
    h = max(1.0, y2 - y1)
    x1 = max(0.0, min(x1, iw - w))
    y1 = max(0.0, min(y1, ih - h))
    return x1, y1, x1 + w, y1 + h


def _apply_edge_min_then_clamp(
    drag_mode: str,
    nx1: float,
    ny1: float,
    nx2: float,
    ny2: float,
    img_width: int,
    img_height: int,
    min_size: int,
) -> Tuple[float, float, float, float]:
    x1, y1, x2, y2 = _normalize_rect(nx1, ny1, nx2, ny2)
    w, h = x2 - x1, y2 - y1
    if drag_mode == "resize_n":
        if h < min_size:
            y1 = y2 - min_size
    elif drag_mode == "resize_s":
        if h < min_size:
            y2 = y1 + min_size
    elif drag_mode == "resize_w":
        if w < min_size:
            x1 = x2 - min_size
    elif drag_mode == "resize_e":
        if w < min_size:
            x2 = x1 + min_size
    return _clamp_inside_image(x1, y1, x2, y2, img_width, img_height)


def _aspect_from_raw(w_raw: float, h_raw: float, ar: float) -> Tuple[float, float]:
    w_raw = max(1.0, w_raw)
    h_raw = max(1.0, h_raw)
    if w_raw / h_raw > ar:
        h = h_raw
        w = ar * h
    else:
        w = w_raw
        h = w / ar
    if w < MIN_CROP_SIZE:
        w = float(MIN_CROP_SIZE)
        h = max(float(MIN_CROP_SIZE), w / ar)
    if h < MIN_CROP_SIZE:
        h = float(MIN_CROP_SIZE)
        w = max(float(MIN_CROP_SIZE), h * ar)
    return w, h


def _corner_drag(
    drag_mode: str,
    mx: float,
    my: float,
    crop_x1: float,
    crop_y1: float,
    crop_x2: float,
    crop_y2: float,
    ar: float,
    iw: int,
    ih: int,
) -> Tuple[float, float, float, float]:
    ar = max(1e-6, ar)
    if drag_mode == "resize_nw":
        fx, fy = crop_x2, crop_y2
        w_raw, h_raw = abs(fx - mx), abs(fy - my)
        w, h = _aspect_from_raw(w_raw, h_raw, ar)
        nx1, ny1, nx2, ny2 = fx - w, fy - h, fx, fy
    elif drag_mode == "resize_se":
        fx, fy = crop_x1, crop_y1
        w_raw, h_raw = abs(mx - fx), abs(my - fy)
        w, h = _aspect_from_raw(w_raw, h_raw, ar)
        nx1, ny1, nx2, ny2 = fx, fy, fx + w, fy + h
    elif drag_mode == "resize_ne":
        fx, fy = crop_x1, crop_y2
        w_raw, h_raw = abs(mx - fx), abs(fy - my)
        w, h = _aspect_from_raw(w_raw, h_raw, ar)
        nx1, ny1, nx2, ny2 = fx, fy - h, fx + w, fy
    elif drag_mode == "resize_sw":
        fx, fy = crop_x2, crop_y1
        w_raw, h_raw = abs(fx - mx), abs(my - fy)
        w, h = _aspect_from_raw(w_raw, h_raw, ar)
        nx1, ny1, nx2, ny2 = fx - w, fy, fx, fy + h
    else:
        return crop_x1, crop_y1, crop_x2, crop_y2
    return _clamp_inside_image(nx1, ny1, nx2, ny2, iw, ih)


def handle_canvas_click(
    event,
    canvas: Canvas,
    canvas_helper: Optional[CanvasHelper],
    crop_x1: float,
    crop_y1: float,
    crop_x2: float,
    crop_y2: float,
    interaction: Interaction,
) -> Tuple[Optional[str], float, float]:
    """Hit-test for resize handles (interaction='resize') or move interior ('move')."""
    if not canvas_helper:
        return None, 0.0, 0.0

    canvas_x = canvas.canvasx(event.x)
    canvas_y = canvas.canvasy(event.y)
    img_x, img_y = canvas_helper.canvas_to_image_coords(canvas_x, canvas_y)

    if interaction == "resize":
        mode = canvas_helper.hit_test_resize_handle(
            img_x, img_y, crop_x1, crop_y1, crop_x2, crop_y2
        )
        return mode, img_x, img_y
    if canvas_helper.hit_test_move_interior(
        img_x, img_y, crop_x1, crop_y1, crop_x2, crop_y2
    ):
        return "move", img_x, img_y
    return None, img_x, img_y


def handle_canvas_drag(
    event,
    canvas: Canvas,
    canvas_helper: Optional[CanvasHelper],
    original_image: Optional[Image.Image],
    drag_mode: Optional[str],
    drag_start_x: float,
    drag_start_y: float,
    crop_x1: float,
    crop_y1: float,
    crop_x2: float,
    crop_y2: float,
    corner_aspect_ratio: Optional[float],
) -> Tuple[float, float, float, float]:
    """Update crop box for move or resize."""
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
        return clamp_crop_to_bounds(
            new_x1, new_y1, new_x2, new_y2, img_width, img_height
        )

    corner_modes = ("resize_nw", "resize_ne", "resize_sw", "resize_se")
    if drag_mode in corner_modes and corner_aspect_ratio and corner_aspect_ratio > 0:
        return _corner_drag(
            drag_mode,
            img_x,
            img_y,
            crop_x1,
            crop_y1,
            crop_x2,
            crop_y2,
            corner_aspect_ratio,
            img_width,
            img_height,
        )

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

    if drag_mode in corner_modes:
        nx1, ny1, nx2, ny2 = _normalize_rect(new_x1, new_y1, new_x2, new_y2)
        return _clamp_inside_image(nx1, ny1, nx2, ny2, img_width, img_height)

    return _apply_edge_min_then_clamp(
        drag_mode,
        new_x1,
        new_y1,
        new_x2,
        new_y2,
        img_width,
        img_height,
        MIN_CROP_SIZE,
    )
