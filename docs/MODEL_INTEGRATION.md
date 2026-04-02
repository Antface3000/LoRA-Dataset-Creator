# Model Integration Guide

This guide explains how to integrate WD14 Tagger and JoyCaption VLM models into the LoRA Dataset Manager.

## WD14 Tagger Integration

### Location
Edit: `core/ai/tagger.py`

### Implementation Steps

1. **Choose your WD14 implementation**:
   - HuggingFace: `SmilingWolf/wd-v1-4-vit-tagger-v2`
   - Local model files
   - Other WD14 variants

2. **Update `load_model()` method** in `WD14Tagger` class:

```python
def load_model(self):
    """Load WD14 model via VRAM manager."""
    if self.model is not None:
        return self.model, self.processor
    
    self.vram_manager.ensure_state(State.CAPTIONING)
    
    try:
        from transformers import AutoModelForImageClassification, AutoProcessor
        
        # Option 1: HuggingFace model
        model_name = "SmilingWolf/wd-v1-4-vit-tagger-v2"
        self.model = AutoModelForImageClassification.from_pretrained(model_name)
        self.processor = AutoProcessor.from_pretrained(model_name)
        
        # Option 2: Local model
        # model_path = Path("path/to/wd14-model")
        # self.model = AutoModelForImageClassification.from_pretrained(str(model_path))
        # self.processor = AutoProcessor.from_pretrained(str(model_path))
        
        # Store in VRAM manager for tracking
        self.vram_manager.wd14_model = self.model
        self.vram_manager.wd14_processor = self.processor
        
        return self.model, self.processor
    except Exception as e:
        raise RuntimeError(f"Failed to load WD14 model: {e}")
```

3. **Update `tag_image()` method** to extract tags:

```python
def tag_image(self, image_path: Path) -> List[str]:
    """Tag image and return list of raw tags."""
    if self.model is None:
        self.load_model()
    
    try:
        image = Image.open(image_path).convert("RGB")
        inputs = self.processor(images=image, return_tensors="pt")
        
        with torch.no_grad():
            outputs = self.model(**inputs)
            # Extract tags from outputs
            # (Implementation depends on model structure)
            tags = self._extract_tags(outputs)
        
        return tags
    except Exception as e:
        print(f"WD14 tagging error: {e}")
        return []
```

## JoyCaption VLM Integration

### Location
Edit: `core/ai/captioner.py`

### Model Placement
Place your JoyCaption model files in an appropriate location (e.g., `models/joycaption/` or similar).

### Implementation Steps

1. **Update `load_model()` method** in `JoyCaption` class:

```python
def load_model(self):
    """Load JoyCaption model via VRAM manager."""
    if self.model is not None:
        return self.model, self.processor
    
    self.vram_manager.ensure_state(State.CAPTIONING)
    
    try:
        from transformers import AutoModelForVision2Seq, AutoProcessor
        from pathlib import Path
        
        # Update this path to where you placed the model
        model_path = Path("path/to/joycaption-model")
        
        self.model = AutoModelForVision2Seq.from_pretrained(str(model_path))
        self.processor = AutoProcessor.from_pretrained(str(model_path))
        
        # Store in VRAM manager for tracking
        self.vram_manager.joycaption_model = self.model
        self.vram_manager.joycaption_processor = self.processor
        
        return self.model, self.processor
    except Exception as e:
        raise RuntimeError(f"Failed to load JoyCaption model: {e}")
```

2. **Update `generate_caption()` method**:

```python
def generate_caption(
    self,
    image_path: Path,
    tags: list[str],
    user_prompt: str = ""
) -> str:
    """Generate natural language caption from image and tags."""
    if self.model is None:
        self.load_model()
    
    try:
        image = Image.open(image_path).convert("RGB")
        
        # Build prompt from tags and user prompt
        tag_string = ", ".join(tags)
        if user_prompt:
            prompt = f"{user_prompt}. Tags: {tag_string}"
        else:
            prompt = f"Describe this image. Tags: {tag_string}"
        
        # Process through VLM
        inputs = self.processor(images=image, text=prompt, return_tensors="pt")
        
        with torch.no_grad():
            outputs = self.model.generate(**inputs)
            caption = self.processor.decode(outputs[0], skip_special_tokens=True)
        
        return caption
    except Exception as e:
        print(f"JoyCaption generation error: {e}")
        # Fallback to tag-based caption
        if tags:
            return ", ".join(tags)
        return "A photograph."
```

## VRAM Manager Integration

The VRAM manager automatically tracks models when you set:
- `self.vram_manager.wd14_model = self.model`
- `self.vram_manager.joycaption_model = self.model`

This ensures proper cleanup when switching tabs.

## Testing

After integrating models:

1. **Test WD14**:
   - Open Caption Editor tab
   - Load an image
   - Click "Generate Caption" (should generate tags first)

2. **Test JoyCaption**:
   - With tags generated, caption should auto-generate
   - Verify caption quality and tag guidance

3. **Test VRAM Management**:
   - Switch between Sort & Crop and Caption Editor tabs
   - Monitor VRAM usage (should stay <12GB)
   - Models should unload when switching away

## Notes

- Models are loaded lazily (only when needed)
- VRAM manager ensures only one model set is loaded at a time
- CLIP model (for aesthetic scoring) loads/unloads quickly and doesn't conflict
- All model loading should handle both CUDA and CPU fallback
