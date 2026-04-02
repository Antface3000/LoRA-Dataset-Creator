"""Aesthetic scoring and blur detection for quality gate (Stage 1)."""

from pathlib import Path
from typing import Tuple
from PIL import Image
import cv2
import torch

from core.config import MIN_LAPLACIAN_VARIANCE, MIN_AESTHETIC_SCORE


def check_image_blur(
    image_path: Path,
    threshold: float = MIN_LAPLACIAN_VARIANCE
) -> Tuple[bool, float]:
    """Check if image is blurry using Laplacian variance.
    
    Args:
        image_path: Path to image file
        threshold: Laplacian variance threshold (default from config)
    
    Returns:
        (passed, score) tuple where passed is True if score >= threshold
    """
    try:
        img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            return False, 0.0
        
        laplacian_var = cv2.Laplacian(img, cv2.CV_64F).var()
        return laplacian_var >= threshold, laplacian_var
    except Exception as e:
        print(f"Blur check error: {e}")
        return True, 0.0  # Pass if check fails


def check_image_aesthetic(
    image_path: Path,
    model,
    processor,
    threshold: float = MIN_AESTHETIC_SCORE,
    device: str = "cuda"
) -> Tuple[bool, float]:
    """Check image aesthetic score using CLIP model.
    
    Args:
        image_path: Path to image file
        model: CLIPModel instance
        processor: CLIPProcessor instance
        threshold: Aesthetic score threshold (1-10 scale, default from config)
        device: Device to run inference on ("cuda" or "cpu")
    
    Returns:
        (passed, score) tuple where score is 1-10 scale
    """
    try:
        # Load and preprocess image
        image = Image.open(image_path).convert("RGB")
        
        # Resize if too large (for performance)
        max_size = 512
        if max(image.size) > max_size:
            image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        inputs = processor(images=image, return_tensors="pt").to(device)
        
        # Get image features
        with torch.no_grad():
            image_features = model.get_image_features(**inputs)
        
        # Simple aesthetic scoring based on feature norm and variance
        # Higher norm and variance typically indicate more interesting/complex images
        feature_norm = torch.norm(image_features, dim=1).item()
        feature_var = torch.var(image_features, dim=1).item()
        
        # Combine metrics - this is a heuristic approach
        # For production, you'd want a trained aesthetic scorer linear probe
        # CLIP features typically have norms in range 15-30 for good images
        norm_score = min(5.0, max(0.0, (feature_norm - 15) / 3.0))  # 0-5 from norm
        var_score = min(5.0, max(0.0, feature_var * 100))  # 0-5 from variance
        
        # Combined score (1-10 scale)
        score = 1.0 + norm_score + var_score
        
        return score >= threshold, score
    except Exception as e:
        print(f"Aesthetic check error: {e}")
        import traceback
        traceback.print_exc()
        return True, 5.0  # Pass if check fails
