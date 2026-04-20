"""Canvas interaction helpers for SortTab."""

from dataclasses import dataclass
from typing import Optional, Tuple
from PIL import Image
from tkinter import Canvas

# Minimum hit margin in image pixels (when canvas is huge)
_MIN_MARGIN_IMAGE = 4.0
# Target hit radius in screen pixels (~handle half-size in overlay)
_TARGET_SCREEN_PX = 10.0


@dataclass(frozen=True)
class ImageCanvasLayout:
    """Bitmap placement matching `update_display` + `create_crop_overlay` / `create_plain_display`."""

    canvas_w: int
    canvas_h: int
    iw: int
    ih: int
    disp_w: int
    disp_h: int
    offset_x: float
    offset_y: float

    @staticmethod
    def compute(canvas_w: int, canvas_h: int, iw: int, ih: int) -> "ImageCanvasLayout":
        if iw <= 0 or ih <= 0:
            dw, dh = max(1, iw), max(1, ih)
            return ImageCanvasLayout(canvas_w, canvas_h, iw, ih, dw, dh, 0.0, 0.0)
        scale = min(canvas_w / iw, canvas_h / ih, 1.0)
        disp_w = max(1, int(iw * scale))
        disp_h = max(1, int(ih * scale))
        offset_x = (canvas_w // 2) - disp_w / 2.0
        offset_y = (canvas_h // 2) - disp_h / 2.0
        return ImageCanvasLayout(
            canvas_w, canvas_h, iw, ih, disp_w, disp_h, offset_x, offset_y
        )

    def canvas_to_image(self, canvas_x: float, canvas_y: float) -> Tuple[float, float]:
        if self.disp_w <= 0 or self.disp_h <= 0:
            return 0.0, 0.0
        img_x = (canvas_x - self.offset_x) * self.iw / self.disp_w
        img_y = (canvas_y - self.offset_y) * self.ih / self.disp_h
        return img_x, img_y


def image_layout_for_canvas(
    canvas_w: int, canvas_h: int, image: Optional[Image.Image]
) -> ImageCanvasLayout:
    """Layout used by both the overlay PhotoImage and hit-testing."""
    if not image:
        return ImageCanvasLayout.compute(canvas_w, canvas_h, 1, 1)
    iw, ih = image.size
    return ImageCanvasLayout.compute(canvas_w, canvas_h, iw, ih)


class CanvasHelper:
    """Helper class for canvas coordinate conversion and interaction."""

    def __init__(self, canvas: Canvas, original_image: Optional[Image.Image]):
        self.canvas = canvas
        self.original_image = original_image

    def _layout(self) -> ImageCanvasLayout:
        cw = self.canvas.winfo_width() if self.canvas.winfo_width() > 1 else 800
        ch = self.canvas.winfo_height() if self.canvas.winfo_height() > 1 else 600
        return image_layout_for_canvas(cw, ch, self.original_image)

    def get_image_scale(self) -> float:
        """Nominal uniform fit scale min(cw/iw, ch/ih, 1) — matches overlay resize factor."""
        if not self.original_image:
            return 1.0
        lay = self._layout()
        return min(lay.canvas_w / lay.iw, lay.canvas_h / lay.ih, 1.0)

    def handle_margin_image(self) -> float:
        """Hit-test margin in image coordinates (~constant on-screen size)."""
        if not self.original_image:
            return 10.0
        lay = self._layout()
        if lay.disp_w <= 0 or lay.disp_h <= 0:
            return 10.0
        m = _TARGET_SCREEN_PX * max(lay.iw / lay.disp_w, lay.ih / lay.disp_h)
        return max(_MIN_MARGIN_IMAGE, m)

    def canvas_to_image_coords(self, canvas_x: float, canvas_y: float) -> Tuple[float, float]:
        """Convert canvas coordinates to image coordinates."""
        if not self.original_image:
            return 0.0, 0.0
        return self._layout().canvas_to_image(canvas_x, canvas_y)

    def hit_test_resize_handle(
        self,
        img_x: float,
        img_y: float,
        crop_x1: float,
        crop_y1: float,
        crop_x2: float,
        crop_y2: float,
    ) -> Optional[str]:
        """Return resize mode for corner/edge handles, or None."""
        m = self.handle_margin_image()
        if img_x <= crop_x1 + m and img_y <= crop_y1 + m:
            return "resize_nw"
        if img_x >= crop_x2 - m and img_y <= crop_y1 + m:
            return "resize_ne"
        if img_x <= crop_x1 + m and img_y >= crop_y2 - m:
            return "resize_sw"
        if img_x >= crop_x2 - m and img_y >= crop_y2 - m:
            return "resize_se"
        if img_y <= crop_y1 + m and crop_x1 + m <= img_x <= crop_x2 - m:
            return "resize_n"
        if img_y >= crop_y2 - m and crop_x1 + m <= img_x <= crop_x2 - m:
            return "resize_s"
        if img_x <= crop_x1 + m and crop_y1 + m <= img_y <= crop_y2 - m:
            return "resize_w"
        if img_x >= crop_x2 - m and crop_y1 + m <= img_y <= crop_y2 - m:
            return "resize_e"
        return None

    def hit_test_move_interior(
        self,
        img_x: float,
        img_y: float,
        crop_x1: float,
        crop_y1: float,
        crop_x2: float,
        crop_y2: float,
    ) -> bool:
        """True if point is inside crop but not on a resize handle."""
        if self.hit_test_resize_handle(img_x, img_y, crop_x1, crop_y1, crop_x2, crop_y2):
            return False
        m = self.handle_margin_image()
        return (
            crop_x1 + m < img_x < crop_x2 - m
            and crop_y1 + m < img_y < crop_y2 - m
        )

    def is_point_in_crop(self, img_x: float, img_y: float,
                         crop_x1: float, crop_y1: float,
                         crop_x2: float, crop_y2: float) -> bool:
        """Check if point is inside crop box (interior, not on handle)."""
        m = self.handle_margin_image()
        return crop_x1 + m <= img_x <= crop_x2 - m and \
               crop_y1 + m <= img_y <= crop_y2 - m
