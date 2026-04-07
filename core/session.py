"""Session dataset model: in-memory list of items until Finalize.

Non-destructive: no disk writes to output until finalize().
Finalize: copy each image to output + write sidecar .txt, then move original to processed folder.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass, field

from core.config import VALID_EXTENSIONS, FOLDER_PROCESSED
from core.data.file_handler import (
    load_image_files,
    copy_image_to_output,
    move_to_processed,
    copy_to_processed,
    write_caption_file,
)
from PIL import Image
from core.telemetry import get_metrics_collector

logger = logging.getLogger(__name__)


@dataclass
class SessionItem:
    """One image in the session: path, optional crop, tags, caption, output name."""
    original_path: Path
    tags: List[str] = field(default_factory=list)
    # Last WD14 tag_image result for this item (manual edits only change `tags`).
    tags_from_scan: List[str] = field(default_factory=list)
    caption: str = ""
    output_stem: Optional[str] = None  # None = use original_path.stem (or with bucket prefix)
    # Optional crop: (x1, y1, x2, y2) in image coords, and bucket for resize
    crop_box: Optional[Tuple[int, int, int, int]] = None
    bucket: str = "square"

    def get_output_stem(self) -> str:
        """Stem used when writing to output (e.g. bucket_originalname or custom)."""
        if self.output_stem:
            return self.output_stem
        return self.original_path.stem

    def get_caption_content(self, tags_only: bool = False, caption_only: bool = False) -> str:
        """Build content for sidecar .txt: tags only, caption only, or both."""
        tags_str = ", ".join(self.tags) if self.tags else ""
        if tags_only:
            return tags_str
        if caption_only:
            return self.caption or ""
        if tags_str and self.caption:
            return tags_str + "\n\n" + self.caption
        return tags_str or self.caption or ""


class Session:
    """Session dataset: source/output dirs, list of items, finalize copies to output and moves originals to processed."""

    def __init__(self):
        self.source_folder: Optional[Path] = None
        self.output_folder: Optional[Path] = None
        self.processed_folder: Optional[Path] = None  # default: source_folder / FOLDER_PROCESSED
        self._items: List[SessionItem] = []
        self._output_format: str = "Both"  # "Tags only" | "Natural language" | "Both"
        self._move_originals: bool = True
        self._finalize_workers: int = 1
        self.metrics = get_metrics_collector()

    @property
    def items(self) -> List[SessionItem]:
        return self._items

    def set_output_format(self, fmt: str) -> None:
        """Set how caption file is built: Tags only, Natural language, Both."""
        self._output_format = fmt

    def set_finalize_behavior(self, move_originals: bool = True, workers: int = 1) -> None:
        """Configure finalize behavior for safety and throughput."""
        self._move_originals = bool(move_originals)
        self._finalize_workers = max(1, int(workers))

    def get_processed_dir(self) -> Optional[Path]:
        """Resolved processed folder: explicit or source_folder/processed."""
        if self.processed_folder is not None:
            return self.processed_folder
        if self.source_folder is not None:
            return self.source_folder / FOLDER_PROCESSED
        return None

    def add_item(self, path: Path) -> bool:
        """Add one image by path. Returns True if added."""
        path = path.resolve()
        if not path.is_file() or path.suffix.lower() not in VALID_EXTENSIONS:
            return False
        if any(item.original_path.resolve() == path for item in self._items):
            return False
        self._items.append(SessionItem(original_path=path))
        return True

    def add_items(self, paths: List[Path]) -> int:
        """Add multiple paths. Returns count added."""
        added = 0
        for p in paths:
            if self.add_item(p):
                added += 1
        return added

    def add_from_source_folder(self) -> int:
        """Load all images from source_folder into session. Returns count added."""
        if not self.source_folder or not self.source_folder.exists():
            return 0
        paths = load_image_files(self.source_folder)
        return self.add_items(paths)

    def remove_item(self, index: int) -> None:
        """Remove item at index."""
        if 0 <= index < len(self._items):
            self._items.pop(index)

    def remove_indices(self, indices: List[int]) -> None:
        """Remove items at indices (sorted descending so order is stable)."""
        for i in sorted(indices, reverse=True):
            self.remove_item(i)

    def rename_item(self, index: int, output_stem: str) -> None:
        """Set output stem for item at index."""
        if 0 <= index < len(self._items):
            self._items[index].output_stem = output_stem.strip() or None

    def reorder(self, new_order: List[int]) -> None:
        """Reorder items; new_order is list of current indices."""
        if len(new_order) != len(self._items):
            return
        self._items = [self._items[i] for i in new_order]

    def update_item(self, index: int, tags: Optional[List[str]] = None, caption: Optional[str] = None,
                    crop_box: Optional[Tuple[int, int, int, int]] = None, bucket: Optional[str] = None) -> None:
        """Update tags, caption, crop for item at index."""
        if index < 0 or index >= len(self._items):
            return
        item = self._items[index]
        if tags is not None:
            item.tags = list(tags)
            item.tags_from_scan = []
        if caption is not None:
            item.caption = caption
        if crop_box is not None:
            item.crop_box = crop_box
        if bucket is not None:
            item.bucket = bucket

    def get_item(self, index: int) -> Optional[SessionItem]:
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def clear(self) -> None:
        """Clear all items (keeps source/output dirs)."""
        self._items.clear()

    def finalize(self, build_caption_content_fn=None) -> Tuple[int, List[str]]:
        """Copy each item to output, write .txt, move original to processed.
        
        build_caption_content_fn(item, output_format) -> str if provided; else use item.get_caption_content.
        Returns (success_count, list of error messages).
        """
        if not self.output_folder:
            return 0, ["Output folder not set"]
        processed_dir = self.get_processed_dir()
        if not processed_dir:
            return 0, ["Processed folder could not be resolved (set source or processed path)"]
        success = 0
        errors: List[str] = []

        def process_item(item: SessionItem) -> Optional[str]:
            try:
                if not item.original_path.exists():
                    return f"Missing: {item.original_path.name}"
                # Build output stem (e.g. bucket_stem)
                stem = item.get_output_stem()
                if item.crop_box and item.original_path.exists():
                    try:
                        img = Image.open(item.original_path).convert("RGB")
                        x1, y1, x2, y2 = item.crop_box
                        cropped = img.crop((x1, y1, x2, y2))
                        from core.ai.cropper import resize_to_bucket
                        resized = resize_to_bucket(cropped, item.bucket)
                        copy_image_to_output(
                            item.original_path,
                            self.output_folder,
                            stem,
                            image=resized
                        )
                    except Exception as e:
                        logger.exception("Crop/save failed for %s: %s", item.original_path.name, e)
                        return f"{item.original_path.name}: {e}"
                else:
                    copy_image_to_output(
                        item.original_path,
                        self.output_folder,
                        stem,
                        image=None
                    )
                # Sidecar .txt: next to the copied image (same stem, .txt)
                out_txt = self.output_folder / f"{stem}.txt"
                if build_caption_content_fn:
                    content = build_caption_content_fn(item, self._output_format)
                else:
                    if self._output_format == "Tags only":
                        content = item.get_caption_content(tags_only=True)
                    elif self._output_format == "Natural language":
                        content = item.get_caption_content(caption_only=True)
                    else:
                        content = item.get_caption_content()
                write_caption_file(out_txt, content)
                # Move or copy original to processed
                if self._move_originals:
                    move_to_processed(item.original_path, processed_dir)
                else:
                    copy_to_processed(item.original_path, processed_dir)
                return None
            except Exception as e:
                logger.exception("Finalize item %s: %s", item.original_path.name, e)
                return f"{item.original_path.name}: {e}"

        with self.metrics.time_stage("stage4_finalize_total", units=len(self._items)):
            if self._finalize_workers == 1:
                for item in self._items:
                    err = process_item(item)
                    if err:
                        errors.append(err)
                    else:
                        success += 1
            else:
                with ThreadPoolExecutor(max_workers=self._finalize_workers) as pool:
                    futures = [pool.submit(process_item, item) for item in self._items]
                    for future in as_completed(futures):
                        err = future.result()
                        if err:
                            errors.append(err)
                        else:
                            success += 1
        return success, errors


_session: Optional[Session] = None


def get_session() -> Session:
    """Get the global session instance."""
    global _session
    if _session is None:
        _session = Session()
    return _session
