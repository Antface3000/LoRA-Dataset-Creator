"""WD14 Tagger - Step 1 of Stage 3 captioning pipeline.

Generates raw tags (e.g., '1girl', 'solo', 'denim_jacket') from images using
SmilingWolf/wd-v1-4-vit-tagger-v2 (ONNX). Captioning always runs tagging first.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from PIL import Image

from core.ai.vram import get_vram_manager, State
from core.config import WD14_MODEL_NAME

logger = logging.getLogger(__name__)


def _load_labels(dataframe) -> tuple:
    """Parse selected_tags.csv: tag names (keep underscores), and indexes for rating (9), general (0), character (4)."""
    tag_names = dataframe["name"].tolist()
    rating_indexes = list(np.where(dataframe["category"] == 9)[0])
    general_indexes = list(np.where(dataframe["category"] == 0)[0])
    character_indexes = list(np.where(dataframe["category"] == 4)[0])
    return tag_names, rating_indexes, general_indexes, character_indexes


class WD14Tagger:
    """WD14 Tagger for image tagging (ONNX model + selected_tags.csv)."""

    def __init__(self):
        self.model = None  # onnx InferenceSession
        self.tag_names: List[str] = []
        self.rating_indexes: List[int] = []
        self.general_indexes: List[int] = []
        self.character_indexes: List[int] = []
        self.model_target_size: int = 448
        self.vram_manager = get_vram_manager()

    def load_model(self) -> Optional[object]:
        """Load WD14 ONNX model and selected_tags.csv from HuggingFace."""
        if self.model is not None:
            logger.debug("WD14 model already loaded")
            return self.model

        self.vram_manager.ensure_state(State.CAPTIONING)

        try:
            import pandas as pd
            from huggingface_hub import hf_hub_download
            import onnxruntime as rt

            model_repo = WD14_MODEL_NAME
            logger.info("Loading WD14 tagger: %s", model_repo)

            csv_path = hf_hub_download(model_repo, "selected_tags.csv")
            model_path = hf_hub_download(model_repo, "model.onnx")

            tags_df = pd.read_csv(csv_path)
            self.tag_names, self.rating_indexes, self.general_indexes, self.character_indexes = _load_labels(tags_df)

            sess_options = rt.SessionOptions()
            sess_options.graph_optimization_level = rt.GraphOptimizationLevel.ORT_ENABLE_ALL
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if self._has_cuda() else ["CPUExecutionProvider"]
            try:
                self.model = rt.InferenceSession(
                    model_path,
                    sess_options,
                    providers=providers,
                )
            except Exception as e:
                if providers != ["CPUExecutionProvider"]:
                    logger.warning("WD14 CUDA provider failed (%s), using CPU", e)
                    self.model = rt.InferenceSession(model_path, sess_options, providers=["CPUExecutionProvider"])
                else:
                    raise
            _, height, width, _ = self.model.get_inputs()[0].shape
            self.model_target_size = height
            self.vram_manager.wd14_model = self.model
            logger.info("WD14 tagger loaded (input size=%s)", self.model_target_size)
            return self.model
        except Exception as e:
            logger.exception("Failed to load WD14 model: %s", e)
            self.model = None
            return None

    def _has_cuda(self) -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except Exception:
            return False

    def _prepare_image(self, image: Image.Image) -> np.ndarray:
        """Pad to square, resize to model size, convert to BGR float32 NCHW-style input."""
        target_size = self.model_target_size
        if image.mode != "RGB":
            image = image.convert("RGB")
        w, h = image.size
        max_dim = max(w, h)
        pad_left = (max_dim - w) // 2
        pad_top = (max_dim - h) // 2
        padded = Image.new("RGB", (max_dim, max_dim), (255, 255, 255))
        padded.paste(image, (pad_left, pad_top))
        if max_dim != target_size:
            padded = padded.resize((target_size, target_size), Image.Resampling.BICUBIC)
        arr = np.asarray(padded, dtype=np.float32)
        arr = arr[:, :, ::-1]  # RGB -> BGR
        return np.expand_dims(arr, axis=0)

    def tag_image(self, image_path: Path, threshold: float = 0.5) -> List[str]:
        """Tag image and return list of raw tags above threshold."""
        if self.model is None:
            self.load_model()
        if self.model is None:
            logger.warning(
                "WD14 model not loaded (load failed—check log for 'Failed to load WD14 model'); using empty tags"
            )
            return []

        try:
            image = Image.open(image_path).convert("RGB")
            input_arr = self._prepare_image(image)
            input_name = self.model.get_inputs()[0].name
            output_name = self.model.get_outputs()[0].name
            preds = self.model.run([output_name], {input_name: input_arr})[0]
            probs = preds[0].astype(float)

            labels = list(zip(self.tag_names, probs))
            general = [(labels[i][0], labels[i][1]) for i in self.general_indexes if labels[i][1] > threshold]
            character = [(labels[i][0], labels[i][1]) for i in self.character_indexes if labels[i][1] > threshold]
            general.sort(key=lambda x: x[1], reverse=True)
            character.sort(key=lambda x: x[1], reverse=True)
            tag_list = [t[0] for t in character + general]
            logger.debug("WD14 tagged %s: %d tags (threshold=%.2f)", image_path.name, len(tag_list), threshold)
            return tag_list
        except Exception as e:
            logger.exception("WD14 tagging error for %s: %s", image_path, e)
            return []

    def tag_images(self, image_paths: List[Path], threshold: float = 0.5) -> Dict[Path, List[str]]:
        """Batch tag images using ONNX batched inference."""
        out: Dict[Path, List[str]] = {}
        if self.model is None:
            self.load_model()
        if self.model is None:
            for path in image_paths:
                out[path] = []
            return out
        if not image_paths:
            return out

        prepared_batches = []
        valid_paths: List[Path] = []
        for path in image_paths:
            try:
                image = Image.open(path).convert("RGB")
                prepared_batches.append(self._prepare_image(image)[0])  # drop batch dim for stacking
                valid_paths.append(path)
            except Exception:
                out[path] = []

        if not prepared_batches:
            return out

        try:
            batch_input = np.stack(prepared_batches, axis=0)
            input_name = self.model.get_inputs()[0].name
            output_name = self.model.get_outputs()[0].name
            preds = self.model.run([output_name], {input_name: batch_input})[0]
            for idx, path in enumerate(valid_paths):
                probs = preds[idx].astype(float)
                labels = list(zip(self.tag_names, probs))
                general = [(labels[i][0], labels[i][1]) for i in self.general_indexes if labels[i][1] > threshold]
                character = [(labels[i][0], labels[i][1]) for i in self.character_indexes if labels[i][1] > threshold]
                general.sort(key=lambda x: x[1], reverse=True)
                character.sort(key=lambda x: x[1], reverse=True)
                out[path] = [t[0] for t in character + general]
        except Exception as e:
            logger.exception("WD14 batch tagging error: %s", e)
            for path in valid_paths:
                out[path] = []
        return out

    def unload_model(self) -> None:
        """Unload model to free VRAM (e.g. before loading Llama)."""
        if self.model is not None:
            self.model = None
        self.tag_names = []
        self.rating_indexes = []
        self.general_indexes = []
        self.character_indexes = []
        if getattr(self.vram_manager, "wd14_model", None) is not None:
            self.vram_manager.wd14_model = None
        import gc
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        gc.collect()
        logger.debug("WD14 model unloaded")


# Global singleton instance
_tagger: Optional[WD14Tagger] = None


def get_tagger() -> WD14Tagger:
    """Get the global WD14 tagger instance."""
    global _tagger
    if _tagger is None:
        _tagger = WD14Tagger()
    return _tagger


def unload_tagger() -> None:
    """Unload the global tagger model to free VRAM."""
    get_tagger().unload_model()


def tag_image(image_path: Path, threshold: float = 0.5) -> List[str]:
    """Convenience function to tag an image."""
    return get_tagger().tag_image(image_path, threshold)


def tag_images(image_paths: List[Path], threshold: float = 0.5) -> Dict[Path, List[str]]:
    """Convenience function to tag images in batch."""
    return get_tagger().tag_images(image_paths, threshold)
