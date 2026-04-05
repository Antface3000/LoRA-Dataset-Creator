"""YOLOv8 person detection and smart cropping logic for Stage 2."""

from pathlib import Path
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from PIL import Image

from core.config import (
    BUCKETS, BUCKET_PORTRAIT, BUCKET_SQUARE, BUCKET_LANDSCAPE,
    YOLO_PERSON_CLASS, DEFAULT_PADDING_MARGIN, RESAMPLING_METHOD
)


@dataclass
class PersonDetection:
    """Person detection result."""
    center_x: float
    center_y: float
    width: float
    height: float
    confidence: float
    aspect_ratio: float


def detect_person(
    image_path: Path,
    model,
    confidence: float = 0.15
) -> Optional[PersonDetection]:
    """Detect person in image using YOLOv8.
    
    Args:
        image_path: Path to image file
        model: YOLOv8 model instance
        confidence: Confidence threshold for detection
    
    Returns:
        PersonDetection if person found, None otherwise
    """
    if model is None:
        return None
    
    try:
        results = model(str(image_path), conf=confidence, verbose=False)
        
        largest_person = None
        largest_area = 0
        
        for result in results:
            boxes = result.boxes
            if boxes is None or len(boxes) == 0:
                continue
            
            # Get all detections
            for i in range(len(boxes)):
                cls = int(boxes.cls[i].cpu().item())
                conf = float(boxes.conf[i].cpu().item())
                
                if cls == YOLO_PERSON_CLASS:  # Person class
                    box = boxes.xyxy[i].cpu().numpy()
                    x1, y1, x2, y2 = box
                    area = (x2 - x1) * (y2 - y1)
                    
                    if area > largest_area:
                        largest_area = area
                        largest_person = {
                            'box': box,
                            'center_x': (x1 + x2) / 2,
                            'center_y': (y1 + y2) / 2,
                            'width': x2 - x1,
                            'height': y2 - y1,
                            'confidence': conf,
                            'area': area
                        }
        
        if largest_person:
            aspect_ratio = largest_person['width'] / largest_person['height']
            return PersonDetection(
                center_x=largest_person['center_x'],
                center_y=largest_person['center_y'],
                width=largest_person['width'],
                height=largest_person['height'],
                confidence=largest_person['confidence'],
                aspect_ratio=aspect_ratio
            )
        
        return None
    except Exception as e:
        print(f"Detection error: {e}")
        return None


def detect_people_batch(
    image_paths: list[Path],
    model,
    confidence: float = 0.15
) -> Dict[Path, Optional[PersonDetection]]:
    """Detect largest person in each image using one batched YOLO call."""
    results_map: Dict[Path, Optional[PersonDetection]] = {p: None for p in image_paths}
    if model is None or not image_paths:
        return results_map

    try:
        results = model([str(p) for p in image_paths], conf=confidence, verbose=False)
        for path, result in zip(image_paths, results):
            boxes = result.boxes
            if boxes is None or len(boxes) == 0:
                continue
            largest_person = None
            largest_area = 0.0
            for i in range(len(boxes)):
                cls = int(boxes.cls[i].cpu().item())
                conf = float(boxes.conf[i].cpu().item())
                if cls != YOLO_PERSON_CLASS:
                    continue
                box = boxes.xyxy[i].cpu().numpy()
                x1, y1, x2, y2 = box
                area = float((x2 - x1) * (y2 - y1))
                if area > largest_area:
                    largest_area = area
                    largest_person = {
                        "center_x": (x1 + x2) / 2,
                        "center_y": (y1 + y2) / 2,
                        "width": x2 - x1,
                        "height": y2 - y1,
                        "confidence": conf,
                    }
            if largest_person:
                aspect_ratio = largest_person["width"] / max(largest_person["height"], 1e-6)
                results_map[path] = PersonDetection(
                    center_x=largest_person["center_x"],
                    center_y=largest_person["center_y"],
                    width=largest_person["width"],
                    height=largest_person["height"],
                    confidence=largest_person["confidence"],
                    aspect_ratio=aspect_ratio,
                )
    except Exception as e:
        print(f"Batch detection error: {e}")
    return results_map


def auto_select_bucket(person_aspect_ratio: Optional[float]) -> str:
    """Automatically select bucket based on detected person aspect ratio.
    
    Args:
        person_aspect_ratio: Aspect ratio of detected person (width/height), or None
    
    Returns:
        'portrait', 'square', or 'landscape'
    """
    if person_aspect_ratio is None:
        return 'square'  # Default to square if no person detected
    
    # Calculate aspect ratios for each bucket
    portrait_aspect = BUCKET_PORTRAIT[0] / BUCKET_PORTRAIT[1]  # ~0.684
    square_aspect = 1.0
    landscape_aspect = BUCKET_LANDSCAPE[0] / BUCKET_LANDSCAPE[1]  # ~1.462
    
    # Find closest bucket
    distances = {
        'portrait': abs(person_aspect_ratio - portrait_aspect),
        'square': abs(person_aspect_ratio - square_aspect),
        'landscape': abs(person_aspect_ratio - landscape_aspect)
    }
    
    return min(distances, key=distances.get)


def detect_bucket_from_dimensions(width: int, height: int) -> str:
    """Return the best-matching bucket name based on image aspect ratio.

    Uses ~15 % tolerance around square so minor variations don't flip bucket.
    portrait  → ratio < 0.87  (e.g. 832×1216 ≈ 0.68)
    landscape → ratio > 1.15  (e.g. 1216×832 ≈ 1.46)
    square    → everything in between
    """
    ratio = width / height if height else 1.0
    if ratio > 1.15:
        return "landscape"
    if ratio < 0.87:
        return "portrait"
    return "square"


def calculate_crop_box(
    image: Image.Image,
    person: Optional[PersonDetection],
    bucket: str,
    padding: int = DEFAULT_PADDING_MARGIN
) -> Tuple[int, int, int, int]:
    """Calculate crop box coordinates.
    
    Args:
        image: PIL Image instance
        person: PersonDetection if person found, None for center crop
        bucket: Bucket type ('portrait', 'square', 'landscape')
        padding: Padding margin around person
    
    Returns:
        (left, top, right, bottom) crop coordinates
    """
    img_width, img_height = image.size
    target_w, target_h = BUCKETS[bucket]
    target_aspect = target_w / target_h
    
    # Compute desired crop dimensions from target aspect ratio
    if target_aspect > 1:  # Landscape
        crop_width = img_height * target_aspect - (padding * 2)
        crop_height = crop_width / target_aspect
    elif target_aspect < 1:  # Portrait
        crop_height = img_width / target_aspect - (padding * 2)
        crop_width = crop_height * target_aspect
    else:  # Square
        crop_size = min(img_width, img_height) - (padding * 2)
        crop_width = crop_size
        crop_height = crop_size

    crop_width = max(100, crop_width)
    crop_height = max(100, crop_height)

    # Scale down proportionally if the desired crop exceeds image bounds —
    # this preserves the target aspect ratio even at image edges.
    if crop_width > img_width or crop_height > img_height:
        fit_scale = min(img_width / crop_width, img_height / crop_height)
        crop_width *= fit_scale
        crop_height *= fit_scale

    if person is not None:
        center_x, center_y = person.center_x, person.center_y
    else:
        center_x, center_y = img_width / 2, img_height / 2

    # Center on subject, clamped so the box never exits the image
    crop_x1 = max(0, min(img_width - crop_width, center_x - crop_width / 2))
    crop_y1 = max(0, min(img_height - crop_height, center_y - crop_height / 2))
    crop_x2 = crop_x1 + crop_width
    crop_y2 = crop_y1 + crop_height

    return (int(crop_x1), int(crop_y1), int(crop_x2), int(crop_y2))


def resize_to_bucket(image: Image.Image, bucket: str) -> Image.Image:
    """Resize image to target bucket resolution using LANCZOS resampling.
    
    Args:
        image: PIL Image to resize
        bucket: Bucket type ('portrait', 'square', 'landscape')
    
    Returns:
        Resized PIL Image
    """
    target_w, target_h = BUCKETS[bucket]
    return image.resize((target_w, target_h), Image.Resampling.LANCZOS)
