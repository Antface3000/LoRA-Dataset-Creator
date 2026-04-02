"""Pipeline Manager - Orchestrates workflow between stages and manages state transitions."""

import logging
from queue import Queue
from pathlib import Path
from typing import Optional, List, Tuple
from PIL import Image

logger = logging.getLogger(__name__)

from core.ai.vram import get_vram_manager, State
from core.config import BUCKETS
from core.telemetry import get_metrics_collector


class PipelineManager:
    """Orchestrates the three-stage pipeline with VRAM-aware state management."""
    
    def __init__(self):
        self.vram_manager = get_vram_manager()
        self.source_folder: Optional[Path] = None
        self.output_folder: Optional[Path] = None
        self.caption_queue: List[Path] = []
        self.metrics = get_metrics_collector()
    
    def switch_to_cropping_tab(self) -> None:
        """Switch to cropping tab - ensures YOLO loaded, unloads captioning models."""
        self.vram_manager.ensure_state(State.CROPPING)
        # YOLO will be loaded lazily when needed
    
    def switch_to_captioning_tab(self) -> None:
        """Switch to captioning tab - ensures WD14+JoyCaption loaded, unloads YOLO."""
        self.vram_manager.ensure_state(State.CAPTIONING)
        # Models will be loaded lazily when needed
    
    def switch_to_idle(self) -> None:
        """Switch to idle state - clears all models."""
        self.vram_manager.ensure_state(State.IDLE)
    
    def process_stage1_quality_gate(
        self,
        image_path: Path,
        mode: str = "blur",  # "blur" or "aesthetic"
        blur_threshold: float = 100.0,
        aesthetic_threshold: float = 5.0,
        rename_with_score: bool = True
    ) -> Tuple[bool, float, Optional[Path]]:
        """Process Stage 1: Quality Gate (The Critic).
        
        Args:
            image_path: Path to image file
            mode: "blur" or "aesthetic"
            blur_threshold: Laplacian variance threshold
            aesthetic_threshold: Aesthetic score threshold (1-10)
            rename_with_score: If True, rename file with score prefix
        
        Returns:
            (passed, score, new_path) tuple where new_path is the renamed path if renamed
        """
        # Import here to avoid circular dependencies
        from core.ai.aesthetic import check_image_blur, check_image_aesthetic
        from core.data.file_handler import rename_with_score as rename_file_with_score
        
        if mode == "blur":
            passed, score = check_image_blur(image_path, blur_threshold)
        else:  # aesthetic
            # Load CLIP model temporarily
            clip_model, clip_processor = self.vram_manager.load_clip_model()
            passed, score = check_image_aesthetic(image_path, clip_model, clip_processor, aesthetic_threshold)
            # Unload CLIP immediately after use to free VRAM
            self.vram_manager.unload_clip_model()
        
        new_path = None
        if passed and rename_with_score and mode == "aesthetic":
            # Rename with score prefix: [Score]_Filename.ext
            new_path = rename_file_with_score(image_path, score)
        
        return passed, score, new_path
    
    def process_stage2_cropping(
        self,
        image_path: Path,
        output_dir: Path,
        bucket: str = "square",
        confidence: float = 0.15,
        padding: int = 50
    ) -> Optional[Path]:
        """Process Stage 2: Aspect Ratio Bucketing & Smart Cropping.
        
        Returns:
            Path to saved cropped image, or None on error
        """
        # Import here to avoid circular dependencies
        from core.ai.cropper import detect_person, calculate_crop_box, resize_to_bucket
        from core.data.file_handler import save_cropped_image_flat

        with self.metrics.time_stage("stage2_crop_single"):
            yolo_model = self.vram_manager.load_yolo()
            image = Image.open(image_path)
            person = detect_person(image_path, yolo_model, confidence)
            crop_box = calculate_crop_box(image, person, bucket, padding)
            cropped = image.crop(crop_box)
            resized = resize_to_bucket(cropped, bucket)
            output_path = save_cropped_image_flat(resized, output_dir, bucket, image_path.stem)

        return output_path

    def process_stage2_cropping_batch(
        self,
        image_paths: List[Path],
        output_dir: Path,
        bucket: str = "square",
        confidence: float = 0.15,
        padding: int = 50,
        auto_bucket: bool = False,
        yolo_batch_size: int = 8,
    ) -> List[Path]:
        """Batch crop images using YOLO batch detection plus queued write stage."""
        from core.ai.cropper import detect_people_batch, calculate_crop_box, resize_to_bucket
        from core.data.file_handler import save_cropped_image_flat

        if not image_paths:
            return []

        yolo_model = self.vram_manager.load_yolo()
        queued_inputs: Queue[tuple[Path, str, Image.Image, tuple[int, int, int, int]]] = Queue()
        written: List[Path] = []

        with self.metrics.time_stage("stage2_crop_batch_total", units=len(image_paths)):
            for i in range(0, len(image_paths), max(1, yolo_batch_size)):
                batch_paths = image_paths[i : i + max(1, yolo_batch_size)]
                people_map = detect_people_batch(batch_paths, yolo_model, confidence)
                for image_path in batch_paths:
                    image = Image.open(image_path)
                    person = people_map.get(image_path)
                    selected_bucket = bucket
                    if auto_bucket and person is not None:
                        selected_bucket = self.select_bucket_for_person(person.aspect_ratio)
                    crop_box = calculate_crop_box(image, person, selected_bucket, padding)
                    queued_inputs.put((image_path, selected_bucket, image, crop_box))

            while not queued_inputs.empty():
                image_path, selected_bucket, image, crop_box = queued_inputs.get()
                cropped = image.crop(crop_box)
                resized = resize_to_bucket(cropped, selected_bucket)
                out = save_cropped_image_flat(resized, output_dir, selected_bucket, image_path.stem)
                written.append(out)

        return written
    
    def process_stage3_captioning(
        self,
        image_path: Path,
        user_prompt: str = ""
    ) -> Tuple[List[str], str]:
        """Process Stage 3: The Gold Standard Captioning.
        
        Tagging is always done first. For natural language captions, the image
        is read by the vision model and tags by the LLM; the LLM combines both
        into a coherent caption.
        
        Returns:
            (tags, caption) tuple
        """
        # Import here to avoid circular dependencies
        from core.ai.tagger import tag_image
        from core.ai.captioner import generate_caption
        
        logger.info("Stage 3 captioning: %s", image_path.name)
        self.vram_manager.ensure_state(State.CAPTIONING)
        
        with self.metrics.time_stage("stage3_caption_single"):
            # Step 1: WD14 tagging (always first; tags are source of truth)
            tags = tag_image(image_path)
            logger.debug("Tags (%d): %s", len(tags), tags[:10] if len(tags) > 10 else tags)

            # Step 2: Vision model reads image, LLM reads tags; model outputs coherent caption
            caption = generate_caption(image_path, tags, user_prompt)
            logger.debug("Caption length: %d", len(caption))
        
        return tags, caption

    def process_stage3_captioning_batch(
        self,
        image_paths: List[Path],
        user_prompt: str = "",
        tag_threshold: float = 0.5,
        tag_batch_size: int = 16,
    ) -> List[Tuple[Path, List[str], str]]:
        """Batch caption stage with WD14 micro-batching and queued caption finalize."""
        from core.ai.tagger import tag_images
        from core.ai.captioner import generate_caption

        queue: Queue[Tuple[Path, List[str]]] = Queue()
        results: List[Tuple[Path, List[str], str]] = []
        if not image_paths:
            return results

        with self.metrics.time_stage("stage3_caption_batch_total", units=len(image_paths)):
            for i in range(0, len(image_paths), max(1, tag_batch_size)):
                batch_paths = image_paths[i : i + max(1, tag_batch_size)]
                batch_tags = tag_images(batch_paths, threshold=tag_threshold)
                for path in batch_paths:
                    queue.put((path, batch_tags.get(path, [])))

            while not queue.empty():
                path, tags = queue.get()
                caption = generate_caption(path, tags, user_prompt)
                results.append((path, tags, caption))
        return results

    def select_bucket_for_person(self, person_aspect_ratio: Optional[float]) -> str:
        """Select an output bucket from detected person ratio."""
        from core.ai.cropper import auto_select_bucket

        return auto_select_bucket(person_aspect_ratio)
    
    def set_folders(self, source_folder: Path, output_folder: Path) -> None:
        """Set source and output folders."""
        self.source_folder = source_folder
        self.output_folder = output_folder
    
    def get_folders(self) -> Tuple[Optional[Path], Optional[Path]]:
        """Get source and output folders."""
        return self.source_folder, self.output_folder

    def add_to_caption_queue(self, path: Path) -> None:
        """Add a cropped image path to the captioning queue."""
        self.caption_queue.append(path)

    def get_caption_queue(self) -> List[Path]:
        """Return a copy of the caption queue."""
        return list(self.caption_queue)

    def pop_next_from_caption_queue(self) -> Optional[Path]:
        """Remove and return the next path in the caption queue, or None if empty."""
        if not self.caption_queue:
            return None
        return self.caption_queue.pop(0)

    def clear_caption_queue(self) -> None:
        """Clear the caption queue."""
        self.caption_queue.clear()


# Global singleton instance
_pipeline_manager: Optional[PipelineManager] = None


def get_pipeline_manager() -> PipelineManager:
    """Get the global pipeline manager instance."""
    global _pipeline_manager
    if _pipeline_manager is None:
        _pipeline_manager = PipelineManager()
    return _pipeline_manager
