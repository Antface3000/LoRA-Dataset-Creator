"""Canvas interaction helpers for SortTab."""

from typing import Optional, Tuple
from PIL import Image
from tkinter import Canvas

# Handle hit-test margin in image coordinates (for corners/edges)
HANDLE_MARGIN = 10


class CanvasHelper:
    """Helper class for canvas coordinate conversion and interaction."""
    
    def __init__(self, canvas: Canvas, original_image: Optional[Image.Image]):
        self.canvas = canvas
        self.original_image = original_image
    
    def canvas_to_image_coords(self, canvas_x: float, canvas_y: float) -> Tuple[float, float]:
        """Convert canvas coordinates to image coordinates."""
        if not self.original_image:
            return 0.0, 0.0
        
        canvas_width  = self.canvas.winfo_width()  if self.canvas.winfo_width()  > 1 else 800
        canvas_height = self.canvas.winfo_height() if self.canvas.winfo_height() > 1 else 600
        img_width, img_height = self.original_image.size
        scale = min(canvas_width / img_width, canvas_height / img_height, 1.0)
        img_x_on_canvas = (canvas_width - img_width * scale) / 2
        img_y_on_canvas = (canvas_height - img_height * scale) / 2
        img_x = (canvas_x - img_x_on_canvas) / scale
        img_y = (canvas_y - img_y_on_canvas) / scale
        return img_x, img_y
    
    def is_point_in_crop(self, img_x: float, img_y: float,
                         crop_x1: float, crop_y1: float,
                         crop_x2: float, crop_y2: float) -> bool:
        """Check if point is inside crop box (interior, not on handle)."""
        return crop_x1 + HANDLE_MARGIN <= img_x <= crop_x2 - HANDLE_MARGIN and \
               crop_y1 + HANDLE_MARGIN <= img_y <= crop_y2 - HANDLE_MARGIN
    
    def hit_test_handle(self, img_x: float, img_y: float,
                        crop_x1: float, crop_y1: float,
                        crop_x2: float, crop_y2: float) -> Optional[str]:
        """Return which handle the point is on: move, resize_nw, resize_ne, resize_sw, resize_se, or edge variants."""
        m = HANDLE_MARGIN
        # Corners (check first)
        if img_x <= crop_x1 + m and img_y <= crop_y1 + m:
            return "resize_nw"
        if img_x >= crop_x2 - m and img_y <= crop_y1 + m:
            return "resize_ne"
        if img_x <= crop_x1 + m and img_y >= crop_y2 - m:
            return "resize_sw"
        if img_x >= crop_x2 - m and img_y >= crop_y2 - m:
            return "resize_se"
        # Edges
        if img_y <= crop_y1 + m and crop_x1 + m <= img_x <= crop_x2 - m:
            return "resize_n"
        if img_y >= crop_y2 - m and crop_x1 + m <= img_x <= crop_x2 - m:
            return "resize_s"
        if img_x <= crop_x1 + m and crop_y1 + m <= img_y <= crop_y2 - m:
            return "resize_w"
        if img_x >= crop_x2 - m and crop_y1 + m <= img_y <= crop_y2 - m:
            return "resize_e"
        # Inside
        if crop_x1 <= img_x <= crop_x2 and crop_y1 <= img_y <= crop_y2:
            return "move"
        return None
