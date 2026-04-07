"""NudeNet body-part detector wrapper.

Uses the NudeNet ONNX model (downloaded automatically on first use, ~45 MB,
cached in %%APPDATA%%/nudenet) to detect anatomical regions in images and
return bounding boxes for use in the Crop & Sort canvas.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Short filename suffix used when saving multiple crops from one image
CLASS_SUFFIXES: Dict[str, str] = {
    "FEMALE_BREAST_EXPOSED":    "breast_exp",
    "FEMALE_BREAST_COVERED":    "breast_cov",
    "FEMALE_GENITALIA_EXPOSED": "genitalia_exp",
    "FEMALE_GENITALIA_COVERED": "genitalia_cov",
    "MALE_GENITALIA_EXPOSED":   "genitalia_m",
    "BUTTOCKS_EXPOSED":         "buttocks",
    "ANUS_EXPOSED":             "anus",
    "FACE_FEMALE":              "face_f",
    "FACE_MALE":                "face_m",
    "BELLY_EXPOSED":            "belly_exp",
    "BELLY_COVERED":            "belly_cov",
    "ARMPITS_EXPOSED":          "armpits",
}

# Full list of classes NudeNet v3 can detect
NUDENET_CLASSES: List[str] = [
    "FEMALE_BREAST_EXPOSED",
    "FEMALE_BREAST_COVERED",
    "FEMALE_GENITALIA_EXPOSED",
    "FEMALE_GENITALIA_COVERED",
    "MALE_GENITALIA_EXPOSED",
    "BUTTOCKS_EXPOSED",
    "ANUS_EXPOSED",
    "FACE_FEMALE",
    "FACE_MALE",
    "BELLY_EXPOSED",
    "BELLY_COVERED",
    "ARMPITS_EXPOSED",
]

# Human-readable display labels for the UI dropdown
DISPLAY_NAMES: Dict[str, str] = {
    "FEMALE_BREAST_EXPOSED":     "Breasts (exposed)",
    "FEMALE_BREAST_COVERED":     "Breasts (covered)",
    "FEMALE_GENITALIA_EXPOSED":  "Female genitalia (exposed)",
    "FEMALE_GENITALIA_COVERED":  "Female genitalia (covered)",
    "MALE_GENITALIA_EXPOSED":    "Male genitalia",
    "BUTTOCKS_EXPOSED":          "Buttocks",
    "ANUS_EXPOSED":              "Anus",
    "FACE_FEMALE":               "Face (female)",
    "FACE_MALE":                 "Face (male)",
    "BELLY_EXPOSED":             "Belly",
    "BELLY_COVERED":             "Belly (covered)",
    "ARMPITS_EXPOSED":           "Armpits",
}

# Reverse lookup: display label → class key
LABEL_TO_CLASS: Dict[str, str] = {v: k for k, v in DISPLAY_NAMES.items()}


def detect_body_parts(
    image_path: Path,
    target_classes: List[str],
    min_score: float = 0.4,
) -> Optional[Dict]:
    """Run NudeNet on *image_path* and return the highest-confidence detection
    that matches one of *target_classes* with score >= *min_score*.

    Returns a dict with keys ``"class"``, ``"score"``, and ``"box"``
    (format: ``[x, y, w, h]`` in image pixel coordinates), or ``None`` if
    nothing is found.

    NudeNet is imported lazily so the rest of the app starts even if the
    package is not installed.
    """
    try:
        from nudenet import NudeDetector  # type: ignore
    except ImportError:
        raise RuntimeError(
            "NudeNet is not installed. Run:  pip install nudenet"
        )

    detector = NudeDetector()
    try:
        results = detector.detect(str(image_path))
    except Exception as exc:
        raise RuntimeError(f"NudeNet detection failed: {exc}") from exc

    matches = [
        r for r in results
        if r.get("class") in target_classes and r.get("score", 0) >= min_score
    ]
    if not matches:
        return None
    return max(matches, key=lambda r: r["score"])


def detect_all_body_parts(
    image_path: Path,
    target_classes: List[str],
    min_score: float = 0.4,
) -> List[Dict]:
    """Run NudeNet on *image_path* and return the best detection for **each**
    checked class that is found above *min_score*.

    Returns a list of dicts (same format as :func:`detect_body_parts`), one
    entry per matched class, sorted by descending confidence.  An empty list
    means no matches.  This is used by the batch crop so that multiple checked
    body parts each produce their own crop from a single image.
    """
    try:
        from nudenet import NudeDetector  # type: ignore
    except ImportError:
        raise RuntimeError("NudeNet is not installed. Run:  pip install nudenet")

    detector = NudeDetector()
    try:
        results = detector.detect(str(image_path))
    except Exception as exc:
        raise RuntimeError(f"NudeNet detection failed: {exc}") from exc

    # For each requested class, union-merge ALL detections above min_score into
    # a single bounding box that covers every detected instance (e.g. both the
    # left and right breast become one wide box instead of two competing boxes).
    union_per_class: Dict[str, Dict] = {}
    for r in results:
        cls = r.get("class")
        score = r.get("score", 0)
        if cls not in target_classes or score < min_score:
            continue
        x, y, w, h = r["box"]  # NudeNet format: [x, y, w, h]
        rx1, ry1, rx2, ry2 = x, y, x + w, y + h
        if cls not in union_per_class:
            union_per_class[cls] = {
                "class": cls, "score": score,
                "_x1": rx1, "_y1": ry1, "_x2": rx2, "_y2": ry2,
            }
        else:
            e = union_per_class[cls]
            e["_x1"] = min(e["_x1"], rx1)
            e["_y1"] = min(e["_y1"], ry1)
            e["_x2"] = max(e["_x2"], rx2)
            e["_y2"] = max(e["_y2"], ry2)
            e["score"] = max(e["score"], score)

    # Convert merged extents back to [x, y, w, h] and clean up temp keys
    for e in union_per_class.values():
        e["box"] = [e["_x1"], e["_y1"], e["_x2"] - e["_x1"], e["_y2"] - e["_y1"]]
        del e["_x1"], e["_y1"], e["_x2"], e["_y2"]

    return sorted(union_per_class.values(), key=lambda r: r["score"], reverse=True)


def box_to_coords(
    box: List[int],
    context_scale: float = 1.5,
    padding: int = 0,
    img_width: int = 0,
    img_height: int = 0,
) -> Tuple[int, int, int, int]:
    """Convert NudeNet ``[x, y, w, h]`` box to ``(x1, y1, x2, y2)``.

    The crop region is expanded proportionally around the detection centre by
    *context_scale* (e.g. 1.5 = 1.5× the detected box width/height on each
    axis, centred on the detection).  An optional *padding* in pixels is then
    added on top of that.  Both are clamped to image bounds when *img_width*
    or *img_height* are provided.
    """
    x, y, w, h = box
    cx = x + w / 2
    cy = y + h / 2
    new_w = w * context_scale
    new_h = h * context_scale
    x1 = max(0, int(cx - new_w / 2) - padding)
    y1 = max(0, int(cy - new_h / 2) - padding)
    x2 = int(cx + new_w / 2) + padding
    y2 = int(cy + new_h / 2) + padding
    if img_width:
        x2 = min(img_width, x2)
    if img_height:
        y2 = min(img_height, y2)
    return x1, y1, x2, y2
