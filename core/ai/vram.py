"""VRAM Manager - Global model lifecycle management for 12GB VRAM limit.

This module enforces Single-Model Residency:
- State.IDLE: No models loaded
- State.CROPPING: YOLO loaded
- State.CAPTIONING: WD14 + JoyCaption loaded
"""

import gc
from enum import Enum
from typing import Optional
import torch


class State(Enum):
    """VRAM state machine states."""
    IDLE = "idle"
    CROPPING = "cropping"  # YOLO loaded
    CAPTIONING = "captioning"  # WD14 + JoyCaption loaded


class VRAMManager:
    """Manages model loading/unloading to stay within 12GB VRAM limit."""
    
    def __init__(self):
        self.current_state = State.IDLE
        self.yolo_model = None
        self.wd14_model = None
        self.joycaption_model = None
        self.joycaption_processor = None
        self.clip_model = None
        self.clip_processor = None
    
    def ensure_state(self, target_state: State) -> None:
        """Ensure we're in the target state, unloading conflicting models."""
        if self.current_state == target_state:
            return
        
        # Unload models that conflict with target state
        if target_state == State.CROPPING:
            self._unload_captioning_models()
            self._unload_clip_model()
        elif target_state == State.CAPTIONING:
            self.unload_yolo()
            self._unload_clip_model()
        elif target_state == State.IDLE:
            self.clear_all()
        
        self.current_state = target_state
    
    def load_yolo(self, model_path: str = "models/yolov8n.pt"):
        """Load YOLOv8 model for person detection."""
        if self.yolo_model is not None:
            return self.yolo_model
        
        self.ensure_state(State.CROPPING)
        
        try:
            from ultralytics import YOLO
            self.yolo_model = YOLO(model_path)
            return self.yolo_model
        except Exception as e:
            raise RuntimeError(f"Failed to load YOLO model: {e}")
    
    def unload_yolo(self) -> None:
        """Unload YOLOv8 model and free VRAM."""
        if self.yolo_model is None:
            return
        
        del self.yolo_model
        self.yolo_model = None
        
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()
        
        if self.current_state == State.CROPPING:
            self.current_state = State.IDLE
    
    def load_captioning_models(self):
        """Load WD14 and JoyCaption models.
        
        Note: Models are actually loaded lazily by tagger.py and captioner.py.
        This method ensures correct VRAM state.
        """
        self.ensure_state(State.CAPTIONING)
        # Return whatever models are currently loaded (may be None if not yet loaded)
        return self.wd14_model, self.joycaption_model

    def prewarm_captioning_models(self) -> None:
        """Eager-load captioning stack once to avoid repeated stall during first generation."""
        self.ensure_state(State.CAPTIONING)
        try:
            from core.ai.tagger import get_tagger
            from core.ai.captioner import get_captioner, get_caption_llama

            get_tagger().load_model()
            captioner = get_captioner()
            captioner.load_model(model_type=captioner.model_type)
            get_caption_llama()
        except Exception:
            # Keep prewarm best-effort; runtime fallbacks still exist.
            pass
    
    def unload_captioning_models(self) -> None:
        """Unload WD14 and JoyCaption models."""
        self._unload_captioning_models()
    
    def _unload_captioning_models(self) -> None:
        """Internal method to unload captioning models."""
        if self.wd14_model is not None:
            del self.wd14_model
            self.wd14_model = None
        
        if self.joycaption_model is not None:
            del self.joycaption_model
            self.joycaption_model = None
        
        if self.joycaption_processor is not None:
            del self.joycaption_processor
            self.joycaption_processor = None
        
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()
        
        if self.current_state == State.CAPTIONING:
            self.current_state = State.IDLE
    
    def load_clip_model(self):
        """Load CLIP model for aesthetic scoring (temporary, can be unloaded quickly)."""
        if self.clip_model is not None and self.clip_processor is not None:
            return self.clip_model, self.clip_processor
        
        try:
            from transformers import CLIPProcessor, CLIPModel
            device = "cuda" if torch.cuda.is_available() else "cpu"
            
            self.clip_model = CLIPModel.from_pretrained("openai/clip-vit-large-patch14").to(device)
            self.clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14")
            self.clip_model.eval()
            
            return self.clip_model, self.clip_processor
        except ImportError:
            raise RuntimeError("Transformers library not installed. Install with: pip install transformers")
    
    def unload_clip_model(self) -> None:
        """Unload CLIP model (used temporarily for aesthetic scoring)."""
        self._unload_clip_model()
    
    def _unload_clip_model(self) -> None:
        """Internal method to unload CLIP model."""
        if self.clip_model is not None:
            del self.clip_model
            self.clip_model = None
        
        if self.clip_processor is not None:
            del self.clip_processor
            self.clip_processor = None
        
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()
    
    def clear_all(self) -> None:
        """Emergency VRAM clear - unload all models."""
        self.unload_yolo()
        self.unload_captioning_models()
        self.unload_clip_model()
        self.current_state = State.IDLE
    
    def get_current_state(self) -> State:
        """Get current VRAM state."""
        return self.current_state


# Global singleton instance
_vram_manager: Optional[VRAMManager] = None


def get_vram_manager() -> VRAMManager:
    """Get the global VRAM manager instance."""
    global _vram_manager
    if _vram_manager is None:
        _vram_manager = VRAMManager()
    return _vram_manager
