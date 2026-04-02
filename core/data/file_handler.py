"""File I/O operations using pathlib.Path exclusively (NO os.path allowed)."""

from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple
from PIL import Image

from core.config import (
    VALID_EXTENSIONS, FOLDERS, FOLDER_REJECTS, FOLDER_BLURRY
)


def load_image_files(source_dir: Path) -> List[Path]:
    """Load all valid image files from source folder.
    
    Args:
        source_dir: Source directory path
    
    Returns:
        Sorted list of image file paths
    """
    if not source_dir.exists() or not source_dir.is_dir():
        return []
    
    image_files = []
    seen_files = set()
    
    # Get all image files directly in source folder (not in subdirectories)
    for file_path in source_dir.iterdir():
        if file_path.is_file():
            # Check if file has valid extension (case-insensitive)
            if file_path.suffix.lower() in VALID_EXTENSIONS:
                # Make sure it's in the source folder itself, not a subfolder
                if file_path.parent.resolve() == source_dir.resolve():
                    # Use normalized path to avoid duplicates
                    normalized_path = file_path.resolve()
                    if normalized_path not in seen_files:
                        seen_files.add(normalized_path)
                        image_files.append(normalized_path)
    
    # Sort and return
    return sorted(image_files)


@lru_cache(maxsize=2048)
def get_image_size_cached(image_path_str: str) -> Tuple[int, int]:
    """Return image size using a small metadata cache."""
    with Image.open(Path(image_path_str)) as img:
        return img.size


@lru_cache(maxsize=256)
def get_preview_thumbnail_cached(image_path_str: str, max_size: Tuple[int, int]) -> Image.Image:
    """Build and cache small preview thumbnails for UI lists."""
    with Image.open(Path(image_path_str)) as img:
        thumb = img.convert("RGB")
        thumb.thumbnail(max_size, Image.Resampling.LANCZOS)
        return thumb.copy()


def move_to_rejects(image_path: Path, rejects_dir: Path) -> Path:
    """Move image to rejects folder.
    
    Args:
        image_path: Path to image file to move
        rejects_dir: Rejects directory path
    
    Returns:
        New path of moved file
    """
    rejects_dir.mkdir(parents=True, exist_ok=True)
    
    dest_path = rejects_dir / image_path.name
    
    # Handle duplicates
    if dest_path.exists():
        base = image_path.stem
        ext = image_path.suffix
        counter = 1
        while dest_path.exists():
            dest_path = rejects_dir / f"{base}_dup{counter}{ext}"
            counter += 1
    
    # Move file
    image_path.rename(dest_path)
    return dest_path


def rename_with_score(image_path: Path, score: float) -> Path:
    """Rename file with aesthetic score prefix: [Score]_Filename.ext
    
    Args:
        image_path: Path to image file
        score: Aesthetic score (1-10 scale)
    
    Returns:
        New path of renamed file
    """
    # Format score to 1 decimal place
    score_str = f"[{score:.1f}]"
    
    # Build new filename
    new_name = f"{score_str}_{image_path.name}"
    new_path = image_path.parent / new_name
    
    # Handle duplicates
    if new_path.exists() and new_path != image_path:
        base = image_path.stem
        ext = image_path.suffix
        counter = 1
        while new_path.exists():
            new_name = f"{score_str}_{base}_dup{counter}{ext}"
            new_path = image_path.parent / new_name
            counter += 1
    
    # Rename file
    if new_path != image_path:
        image_path.rename(new_path)
    
    return new_path


def save_cropped_image(
    image: Image.Image,
    output_dir: Path,
    bucket: str,
    original_name: str
) -> Path:
    """Save cropped image to appropriate bucket subfolder (legacy).
    
    Args:
        image: PIL Image to save
        output_dir: Output directory path
        bucket: Bucket type ('portrait', 'square', 'landscape')
        original_name: Original filename (without extension)
    
    Returns:
        Path to saved image
    """
    subfolder = FOLDERS.get(bucket, FOLDERS['square'])
    bucket_dir = output_dir / subfolder
    bucket_dir.mkdir(parents=True, exist_ok=True)
    output_path = bucket_dir / f"{original_name}.png"
    if output_path.exists():
        counter = 1
        while output_path.exists():
            output_path = bucket_dir / f"{original_name}_dup{counter}.png"
            counter += 1
    image.save(output_path, "PNG")
    return output_path


def save_cropped_image_flat(
    image: Image.Image,
    output_dir: Path,
    bucket: str,
    original_name: str
) -> Path:
    """Save cropped image to a single output folder with bucket in filename.
    
    Saves as output_dir / "{bucket}_{original_name}.png" (no subfolders).
    
    Args:
        image: PIL Image to save
        output_dir: Output directory path (single folder)
        bucket: Bucket type ('portrait', 'square', 'landscape')
        original_name: Original filename (without extension)
    
    Returns:
        Path to saved image
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{bucket}_{original_name}.png"
    if output_path.exists():
        counter = 1
        while output_path.exists():
            output_path = output_dir / f"{bucket}_{original_name}_dup{counter}.png"
            counter += 1
    image.save(output_path, "PNG")
    return output_path


def create_output_structure(output_dir: Path) -> None:
    """Create output folder (single directory). Reject/blurry folders for quality filter only.
    
    Args:
        output_dir: Output directory path
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / FOLDER_REJECTS).mkdir(exist_ok=True)
    (output_dir / FOLDER_BLURRY).mkdir(exist_ok=True)


def write_caption_file(path: Path, content: str) -> None:
    """Write caption/tags content to a same-named .txt file.
    
    Args:
        path: Full path to the .txt file (e.g. output_dir / "portrait_foo.txt")
        content: Text to write (tags only, natural language, or both)
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def create_reject_folders(source_dir: Path) -> None:
    """Create reject folders in source directory.
    
    Args:
        source_dir: Source directory path
    """
    source_dir.mkdir(parents=True, exist_ok=True)
    
    # Create reject folders
    (source_dir / FOLDER_REJECTS).mkdir(exist_ok=True)
    (source_dir / FOLDER_BLURRY).mkdir(exist_ok=True)


def copy_image_to_output(
    source_path: Path,
    output_dir: Path,
    output_stem: str,
    image: Optional[Image.Image] = None
) -> Path:
    """Copy image to output directory with given stem; or save provided PIL Image (e.g. cropped).
    
    Args:
        source_path: Original file path (used for extension if image is None)
        output_dir: Output directory path
        output_stem: Output filename without extension
        image: If provided, save this image as PNG; otherwise copy source_path (keeping extension)
    
    Returns:
        Path to the written file
    """
    from core.config import VALID_EXTENSIONS
    output_dir.mkdir(parents=True, exist_ok=True)
    if image is not None:
        ext = ".png"
        out_path = output_dir / f"{output_stem}{ext}"
    else:
        ext = source_path.suffix.lower() if source_path.suffix.lower() in VALID_EXTENSIONS else ".png"
        out_path = output_dir / f"{output_stem}{ext}"
    if out_path.exists():
        counter = 1
        while out_path.exists():
            out_path = output_dir / f"{output_stem}_dup{counter}{ext}"
            counter += 1
    if image is not None:
        image.save(out_path, "PNG")
    else:
        import shutil
        shutil.copy2(source_path, out_path)
    return out_path


def move_to_processed(original_path: Path, processed_dir: Path) -> Path:
    """Move original file into processed folder (e.g. source_folder/processed).
    
    Args:
        original_path: Path to the file to move
        processed_dir: Processed directory path (e.g. source_dir / "processed")
    
    Returns:
        New path of moved file
    """
    processed_dir.mkdir(parents=True, exist_ok=True)
    dest_path = processed_dir / original_path.name
    if dest_path.exists():
        base = original_path.stem
        ext = original_path.suffix
        counter = 1
        while dest_path.exists():
            dest_path = processed_dir / f"{base}_dup{counter}{ext}"
            counter += 1
    original_path.rename(dest_path)
    return dest_path


def copy_to_processed(original_path: Path, processed_dir: Path) -> Path:
    """Copy original file into processed folder without removing source."""
    processed_dir.mkdir(parents=True, exist_ok=True)
    dest_path = processed_dir / original_path.name
    if dest_path.exists():
        base = original_path.stem
        ext = original_path.suffix
        counter = 1
        while dest_path.exists():
            dest_path = processed_dir / f"{base}_dup{counter}{ext}"
            counter += 1
    import shutil
    shutil.copy2(original_path, dest_path)
    return dest_path
