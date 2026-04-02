"""Caption pipeline: WD14 tags -> JoyCaption vision description -> Wizard-Vicuna final caption.

Flow: WD14 (tags) -> JoyCaption (vision-only description) -> Wizard-Vicuna 7B (text-only)
parses tags + vision description and outputs natural language caption to file.
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional
from PIL import Image
import torch

logger = logging.getLogger(__name__)

from core.ai.vram import get_vram_manager, State
from core.config import (
    JOYCAPTION_MODEL_PATH, GEMMA3_MODEL_PATH, FLORENCE2_MODEL_PATH,
    OLLAMA_BASE_DIR, GEMMA3_OLLAMA_PATH, CAPTION_SYSTEM_PROMPT,
    CAPTION_LLAMA_GGUF_PATH,
)
from core import config as core_config
from core.data.profiles import get_profiles_manager


def _clean_caption(caption: str) -> str:
    """Remove echoed 'Tags: ...' or tag-list suffix; return prose-only caption."""
    if not caption or not caption.strip():
        return caption
    # Drop any line that starts with "Tags:" (model echoing the prompt)
    lines = caption.split("\n")
    kept = []
    for line in lines:
        if re.match(r"^\s*[Tt]ags\s*:\s*", line.strip()):
            break
        kept.append(line)
    caption = "\n".join(kept).strip()
    # Same-line suffix: remove " Tags: ..." or " tags: ..." at the end
    match = re.search(r"\s+[Tt]ags\s*:\s*[^\n]+$", caption)
    if match:
        caption = caption[: match.start()].strip()
    return caption.strip()


def _post_process_caption(caption: str) -> str:
    """Apply find/replace rules and append trigger words. Reads from config at call time."""
    if not caption or not caption.strip():
        return caption
    find_replace = getattr(core_config, "CAPTION_FIND_REPLACE", None) or []
    for find_str, replace_str in find_replace:
        caption = caption.replace(find_str, replace_str)
    trigger = (getattr(core_config, "CAPTION_TRIGGER_WORDS", None) or "").strip()
    if trigger:
        caption = caption.rstrip() + " " + trigger
    return caption


# Text-only Llama for final caption (tags + vision description -> prose)
_caption_llama: Optional[object] = None


def get_caption_llama():
    """Load and return the caption LLM (Wizard-Vicuna 7B Uncensored GGUF) for caption finalization."""
    global _caption_llama
    if _caption_llama is not None:
        return _caption_llama
    if not CAPTION_LLAMA_GGUF_PATH.exists() or not CAPTION_LLAMA_GGUF_PATH.is_file():
        logger.warning("Caption LLM path missing or not a file: %s", CAPTION_LLAMA_GGUF_PATH)
        return None
    try:
        from llama_cpp import Llama
        base_kw = dict(
            model_path=str(CAPTION_LLAMA_GGUF_PATH),
            n_ctx=2048,
            n_threads=4,
            n_gpu_layers=-1 if torch.cuda.is_available() else 0,
            verbose=False,
        )
        try:
            _caption_llama = Llama(**base_kw, chat_format="vicuna")
        except TypeError:
            _caption_llama = Llama(**base_kw)
        logger.info("Loaded caption LLM (Wizard-Vicuna): %s", CAPTION_LLAMA_GGUF_PATH.name)
    except Exception as e:
        logger.exception("Failed to load caption LLM: %s", e)
        _caption_llama = None
    return _caption_llama


def _get_active_system_prompt() -> str:
    """Return the active caption LLM system prompt (per-profile override or default)."""
    try:
        profiles = get_profiles_manager()
        prompt = profiles.get_caption_system_prompt()
        if prompt:
            return prompt
    except Exception:
        pass
    return (
        "You are a dataset captioning tool for LoRA training. You receive tags (source of truth) and a vision description. "
        "Your output must be exactly one coherent caption of 1-2 sentences. Do not refuse, add disclaimers, or comment. "
        "RULES: (1) Incorporate every tag in the caption—do not omit or skip any. "
        "(2) Use the same specific terms as the tags; do not replace them with euphemisms or vaguer words. "
        "(3) The caption is for training a model that does not know explicit details; the tags supply that—your job is to "
        "weave every tag into natural prose at the same specificity. Output only the caption text, nothing else."
    )


def _llama_finalize_caption(tags: list, vision_description: str, user_prompt: str = "") -> str:
    """Send tags + vision description to caption LLM (Vicuna); return one coherent natural language caption."""
    llama = get_caption_llama()
    if llama is None:
        logger.warning("Caption LLM not available; using fallback (vision_desc or tags)")
        fallback = vision_description if vision_description.strip() else ", ".join(tags) if tags else "A photograph."
        return _post_process_caption(fallback)
    tag_string = ", ".join(tags) if tags else "(none)"
    logger.debug("Caption LLM finalize: %d tags, vision_desc len=%d", len(tags), len(vision_description or ""))
    user_content = (
        f"Tags (you must use every one in your caption, same specificity—no omissions, no euphemisms):\n{tag_string}\n\n"
        f"Vision description: {vision_description}\n\n"
    )
    if user_prompt:
        user_content += f"Additional guidance: {user_prompt}\n\n"
    user_content += (
        "Write one coherent caption (1-2 sentences) that incorporates every tag above in natural prose. "
        "Do not omit any tag. Do not replace any tag with a softer or vaguer word."
    )
    # Vicuna has no system role; combine system instruction with user content into one user message
    system_prompt = _get_active_system_prompt()
    combined = system_prompt + "\n\n" + user_content
    messages = [{"role": "user", "content": combined}]
    try:
        response = llama.create_chat_completion(
            messages=messages,
            max_tokens=150,
            temperature=0.3,
            stop=["</s>", "\nUSER:", "\n\n\n"],
        )
        caption = response["choices"][0]["message"]["content"].strip()
        out = _clean_caption(caption) if caption else vision_description or ", ".join(tags[:10])
        out = _post_process_caption(out)
        logger.debug("Caption LLM output length: %d", len(out))
        return out
    except Exception as e:
        logger.exception("Caption LLM error: %s", e)
        fallback = vision_description if vision_description.strip() else ", ".join(tags) if tags else "A photograph."
        return _post_process_caption(fallback)


class JoyCaption:
    """JoyCaption VLM for natural language caption generation."""
    
    def __init__(self):
        self.model = None
        self.processor = None
        self.vram_manager = get_vram_manager()
        self.is_gguf = False  # Track if using GGUF format
        # Model selection: "joycaption", "gemma3", or "florence2"
        self.model_type = "joycaption"  # Change to "gemma3" or "florence2" to use different models
        self._resolved_model_paths: dict[str, Path] = {}
    
    def load_model(self, model_type: str = None):
        """Load captioning model via VRAM manager.
        
        Args:
            model_type: "joycaption", "gemma3", or "florence2". If None, uses self.model_type
        """
        if self.model is not None:
            return self.model, self.processor
        
        # Ensure we're in captioning state
        self.vram_manager.ensure_state(State.CAPTIONING)
        
        # Use provided model_type or default to instance setting
        if model_type is None:
            model_type = self.model_type
        
        try:
            from transformers import (
                AutoModel, AutoModelForVision2Seq, AutoModelForImageTextToText,
                AutoProcessor, AutoModelForCausalLM, AutoConfig
            )
            
            # Determine which model to load
            if model_type == "gemma3":
                # Try custom Ollama path first, then default models directory
                if GEMMA3_OLLAMA_PATH and GEMMA3_OLLAMA_PATH.exists():
                    model_path = GEMMA3_OLLAMA_PATH
                elif OLLAMA_BASE_DIR.exists():
                    # Look for Gemma models in Ollama directory
                    gemma_dirs = [d for d in OLLAMA_BASE_DIR.iterdir() if d.is_dir() and "gemma" in d.name.lower()]
                    if gemma_dirs:
                        model_path = gemma_dirs[0]  # Use first Gemma model found
                    else:
                        model_path = GEMMA3_MODEL_PATH
                else:
                    model_path = GEMMA3_MODEL_PATH
                model_name = "Gemma3"
            elif model_type == "florence2":
                model_path = FLORENCE2_MODEL_PATH
                model_name = "Florence2"
            else:  # Default to joycaption
                model_path = JOYCAPTION_MODEL_PATH
                model_name = "JoyCaption"
            
            # Check cached path first to avoid repeated expensive directory scans.
            cached_path = self._resolved_model_paths.get(model_type)
            if cached_path and cached_path.exists() and (cached_path / "config.json").exists():
                model_path = cached_path

            # Check if model directory exists (try direct path first, then subdirectories)
            actual_model_path = None
            if model_path.exists() and (model_path / "config.json").exists():
                actual_model_path = model_path
            else:
                # Look for model in subdirectories (common when models are nested)
                # Check known nested paths first
                known_paths = {
                    "joycaption": [
                        model_path / "llama-joycaption-beta-one",
                        model_path / "joycaption",
                    ],
                    "florence2": [
                        model_path / "Florence-2-base",
                        model_path / "florence2",
                    ],
                    "gemma3": [
                        model_path / "gemma3",
                    ]
                }
                
                # Try known paths for this model type
                if model_type in known_paths:
                    for known_path in known_paths[model_type]:
                        if known_path.exists() and (known_path / "config.json").exists():
                            actual_model_path = known_path
                            print(f"Found {model_name} at: {actual_model_path}")
                            break
                
                # If not found in known paths, search recursively
                if actual_model_path is None and model_path.parent.exists():
                    for subdir in model_path.parent.iterdir():
                        if subdir.is_dir():
                            # Check if this subdirectory contains model files
                            if (subdir / "config.json").exists():
                                actual_model_path = subdir
                                print(f"Found {model_name} at: {actual_model_path}")
                                break
                            # Also check nested subdirectories
                            for nested in subdir.iterdir():
                                if nested.is_dir() and (nested / "config.json").exists():
                                    actual_model_path = nested
                                    print(f"Found {model_name} at: {actual_model_path}")
                                    break
                                if actual_model_path:
                                    break
            
            if actual_model_path is None:
                print(f"Warning: {model_name} model not found at {model_path}")
                print(f"Please place your {model_name} model files in: {model_path}")
                print(f"Or in a subdirectory of: {model_path.parent}")
                return None, None
            
            model_path = actual_model_path
            self._resolved_model_paths[model_type] = model_path
            
            # Check for GGUF files first (priority over HuggingFace format)
            gguf_files = list(model_path.glob("*.gguf"))
            if gguf_files:
                print(f"Detected GGUF files in {model_path}")
                # Find main model and mmproj files
                main_model_file = None
                mmproj_file = None
                
                for gguf_file in gguf_files:
                    name = gguf_file.name.lower()
                    if "mmproj" in name:
                        mmproj_file = gguf_file
                    elif "hf-llava" in name or "llava" in name:
                        main_model_file = gguf_file
                
                # If we found both files, load GGUF model
                if main_model_file and mmproj_file:
                    print(f"Loading GGUF model: {main_model_file.name}")
                    print(f"Loading mmproj: {mmproj_file.name}")
                    try:
                        from llama_cpp import Llama
                        from llama_cpp.llama_chat_format import Llava15ChatHandler
                        from PIL import Image
                        
                        # Load the multimodal projector first (needed for chat handler)
                        chat_handler = Llava15ChatHandler(clip_model_path=str(mmproj_file))
                        
                        # Load the main model with the chat handler
                        self.model = Llama(
                            model_path=str(main_model_file),
                            chat_handler=chat_handler,
                            n_ctx=4096,  # Context window
                            n_threads=4,  # CPU threads
                            n_gpu_layers=-1 if torch.cuda.is_available() else 0,  # Use GPU if available
                            verbose=False
                        )
                        
                        # Store chat handler for later use
                        self.processor = chat_handler
                        self.is_gguf = True
                        print(f"Successfully loaded GGUF model: {main_model_file.name}")
                        return self.model, self.processor
                    except ImportError:
                        print("Error: llama-cpp-python not installed. Install with: pip install llama-cpp-python")
                        return None, None
                    except Exception as e:
                        print(f"Error loading GGUF model: {e}")
                        import traceback
                        traceback.print_exc()
                        return None, None
                elif main_model_file:
                    print(f"Warning: Found main GGUF model but missing mmproj file")
                    print(f"Main model: {main_model_file.name}")
                    print(f"Expected mmproj file with 'mmproj' in the name")
                else:
                    print(f"Warning: Found GGUF files but could not identify main model")
                    for f in gguf_files:
                        print(f"  - {f.name}")
            
            # Load device
            device = "cuda" if torch.cuda.is_available() else "cpu"
            
            # Try to detect model type from config.json (skip if it fails)
            detected_model_type = None
            try:
                import json
                config_path = model_path / "config.json"
                if config_path.exists():
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config_dict = json.load(f)
                        detected_model_type = config_dict.get('model_type')
                        if detected_model_type:
                            print(f"Detected model type from config.json: {detected_model_type}")
            except Exception as e:
                print(f"Note: Could not read config.json directly: {e}")
            
            # Mark as not GGUF for HuggingFace loading
            self.is_gguf = False
            
            # Skip AutoConfig check if config.json read failed - it will likely fail too
            # and we'll rely on trust_remote_code=True to load the model
            
            # Try to load model - Florence2 uses a specific class
            if model_type == "florence2":
                try:
                    # Florence2 uses AutoModelForCausalLM per its auto_map
                    self.model = AutoModelForCausalLM.from_pretrained(
                        str(model_path),
                        dtype=torch.float16 if device == "cuda" else torch.float32,
                        device_map="auto" if device == "cuda" else None,
                        trust_remote_code=True  # Required for Florence2 custom classes
                    )
                    if device == "cpu":
                        self.model = self.model.to(device)
                    self.processor = AutoProcessor.from_pretrained(
                        str(model_path),
                        trust_remote_code=True
                    )
                    self.model.eval()
                    # Store in VRAM manager
                    self.vram_manager.joycaption_model = self.model
                    self.vram_manager.joycaption_processor = self.processor
                    print(f"Successfully loaded {model_name} model from {model_path}")
                    return self.model, self.processor
                except Exception as e:
                    raise RuntimeError(f"Failed to load {model_name} model: {e}")
            else:
                # Check detected model type from config.json
                detected_model_type = None
                try:
                    import json
                    config_path = model_path / "config.json"
                    if config_path.exists():
                        with open(config_path, 'r', encoding='utf-8') as f:
                            config_dict = json.load(f)
                            detected_model_type = config_dict.get('model_type')
                            print(f"Detected model type: {detected_model_type}")
                except Exception as e:
                    print(f"Could not read config.json: {e}")
                
                # Try multiple loading strategies based on detected model type
                loaded = False
                last_error = None
                
                # Strategy 1: For LLaVA models, use AutoModelForVision2Seq or AutoModelForImageTextToText
                if detected_model_type == "llava":
                    # Check if model files exist
                    import json
                    index_file = model_path / "model.safetensors.index.json"
                    missing_files = []
                    if index_file.exists():
                        with open(index_file, 'r') as f:
                            index_data = json.load(f)
                            weight_map = index_data.get('weight_map', {})
                            # Get unique safetensors filenames
                            safetensors_files = set(weight_map.values())
                            for safetensors_file in safetensors_files:
                                if not (model_path / safetensors_file).exists():
                                    missing_files.append(safetensors_file)
                    
                    if missing_files:
                        print(f"Warning: Missing model weight files for {model_name}:")
                        for f in missing_files:
                            print(f"  - {f}")
                        print(f"Please ensure all model files are in: {model_path}")
                        return None, None
                    
                    try:
                        # LLaVA models work with Vision2Seq or ImageTextToText
                        try:
                            self.model = AutoModelForImageTextToText.from_pretrained(
                                str(model_path),
                                dtype=torch.float16 if device == "cuda" else torch.float32,
                                device_map="auto" if device == "cuda" else None,
                                trust_remote_code=True
                            )
                        except:
                            # Fallback to Vision2Seq for older LLaVA versions
                            self.model = AutoModelForVision2Seq.from_pretrained(
                                str(model_path),
                                dtype=torch.float16 if device == "cuda" else torch.float32,
                                device_map="auto" if device == "cuda" else None,
                                trust_remote_code=True
                            )
                        if device == "cpu":
                            self.model = self.model.to(device)
                        self.processor = AutoProcessor.from_pretrained(str(model_path), trust_remote_code=True)
                        loaded = True
                        print(f"Loaded {model_name} (LLaVA) using Vision2Seq/ImageTextToText")
                    except Exception as e:
                        last_error = e
                        print(f"LLaVA loading failed: {e}")
                
                # Strategy 2: Try AutoModelForImageTextToText (newer replacement for Vision2Seq)
                if not loaded:
                    try:
                        self.model = AutoModelForImageTextToText.from_pretrained(
                            str(model_path),
                            dtype=torch.float16 if device == "cuda" else torch.float32,
                            device_map="auto" if device == "cuda" else None,
                            trust_remote_code=True
                        )
                        if device == "cpu":
                            self.model = self.model.to(device)
                        self.processor = AutoProcessor.from_pretrained(str(model_path), trust_remote_code=True)
                        loaded = True
                        print(f"Loaded {model_name} using AutoModelForImageTextToText")
                    except Exception as e:
                        last_error = e
                
                # Strategy 3: Try AutoModelForVision2Seq (deprecated but still works)
                if not loaded:
                    try:
                        self.model = AutoModelForVision2Seq.from_pretrained(
                            str(model_path),
                            dtype=torch.float16 if device == "cuda" else torch.float32,
                            device_map="auto" if device == "cuda" else None,
                            trust_remote_code=True
                        )
                        if device == "cpu":
                            self.model = self.model.to(device)
                        self.processor = AutoProcessor.from_pretrained(str(model_path), trust_remote_code=True)
                        loaded = True
                        print(f"Loaded {model_name} using AutoModelForVision2Seq")
                    except Exception as e:
                        last_error = e
                
                # Strategy 3: Try AutoModel (generic, works with trust_remote_code)
                # This should work even if model_type is not recognized
                # Disabled by default because config mutation/probing can be slow and brittle.
                enable_deep_probe = os.getenv("ENABLE_CAPTION_DEEP_PROBE", "").strip() == "1"
                if not loaded and enable_deep_probe:
                    try:
                        # Try to patch config.json if model_type is missing
                        import json
                        import shutil
                        config_path = model_path / "config.json"
                        config_backup_path = model_path / "config.json.backup"
                        
                        if config_path.exists():
                            # Read config
                            with open(config_path, 'r', encoding='utf-8') as f:
                                config_dict = json.load(f)
                            
                            # If model_type is missing or unrecognized, try to fix it
                            if 'model_type' not in config_dict or config_dict.get('model_type') not in ['llava', 'qwen2_vl', 'clip', 'blip', 'instructblip']:
                                # Backup original config
                                if not config_backup_path.exists():
                                    shutil.copy2(config_path, config_backup_path)
                                
                                # Try to infer from architecture
                                arch = config_dict.get('architectures', [])
                                if arch and len(arch) > 0:
                                    arch_name = arch[0].lower()
                                    # Map common architecture names to model types
                                    if 'llava' in arch_name:
                                        config_dict['model_type'] = 'llava'
                                    elif 'qwen' in arch_name and 'vl' in arch_name:
                                        config_dict['model_type'] = 'qwen2_vl'
                                    elif 'vision' in arch_name or 'clip' in arch_name:
                                        config_dict['model_type'] = 'clip'
                                    elif 'blip' in arch_name:
                                        config_dict['model_type'] = 'blip'
                                    else:
                                        # Use a generic recognized type as fallback
                                        config_dict['model_type'] = 'llava'  # Common VLM type
                                    
                                    # Write patched config
                                    with open(config_path, 'w', encoding='utf-8') as f:
                                        json.dump(config_dict, f, indent=2)
                                    print(f"Patched config.json with model_type: {config_dict.get('model_type')}")
                        
                        # Try loading with trust_remote_code
                        self.model = AutoModel.from_pretrained(
                            str(model_path),
                            dtype=torch.float16 if device == "cuda" else torch.float32,
                            device_map="auto" if device == "cuda" else None,
                            trust_remote_code=True,
                            local_files_only=True
                        )
                        if device == "cpu":
                            self.model = self.model.to(device)
                        self.processor = AutoProcessor.from_pretrained(
                            str(model_path), 
                            trust_remote_code=True,
                            local_files_only=True
                        )
                        loaded = True
                        print(f"Loaded {model_name} using AutoModel (generic with trust_remote_code)")
                    except Exception as e:
                        last_error = e
                        print(f"AutoModel loading failed: {e}")
                        # Restore backup if we modified config
                        if config_backup_path.exists() and config_path.exists():
                            try:
                                shutil.copy2(config_backup_path, config_path)
                                print("Restored original config.json")
                            except:
                                pass
                
                # Strategy 4: Try CausalLM (for text-only models)
                if not loaded:
                    try:
                        self.model = AutoModelForCausalLM.from_pretrained(
                            str(model_path),
                            dtype=torch.float16 if device == "cuda" else torch.float32,
                            device_map="auto" if device == "cuda" else None,
                            trust_remote_code=True
                        )
                        if device == "cpu":
                            self.model = self.model.to(device)
                        self.processor = AutoProcessor.from_pretrained(str(model_path), trust_remote_code=True)
                        loaded = True
                        print(f"Loaded {model_name} using AutoModelForCausalLM")
                    except Exception as e:
                        last_error = e
                
                if not loaded:
                    # Instead of raising an error, return None and let the fallback handle it
                    print(f"Warning: Could not load {model_name} model after trying all strategies.")
                    print(f"Last error: {last_error}")
                    print(f"Will use tag-based caption fallback.")
                    return None, None
            
            self.model.eval()
            
            # Store in VRAM manager for state tracking
            self.vram_manager.joycaption_model = self.model
            self.vram_manager.joycaption_processor = self.processor
            
            print(f"Successfully loaded {model_name} model from {model_path}")
            return self.model, self.processor
        except Exception as e:
            raise RuntimeError(f"Failed to load model: {e}")
    
    def _run_vision_inference(self, image_path: Path, prompt_text: str) -> str:
        """Run vision model on image with the given prompt; return model output (vision description)."""
        if self.model is None:
            self.load_model(model_type=self.model_type)
        if self.model is None:
            logger.warning("JoyCaption model not loaded; vision inference skipped")
            return ""
        logger.debug("Vision inference: %s", image_path.name)
        try:
            image = Image.open(image_path).convert("RGB")
            device = "cuda" if torch.cuda.is_available() else "cpu"
            if self.is_gguf:
                image_url_str = image_path.resolve().as_uri()
                messages = []
                if CAPTION_SYSTEM_PROMPT:
                    messages.append({"role": "system", "content": CAPTION_SYSTEM_PROMPT})
                messages.append({
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_url_str}},
                        {"type": "text", "text": prompt_text}
                    ]
                })
                response = self.model.create_chat_completion(
                    messages=messages,
                    max_tokens=150,
                    temperature=0.7,
                    stop=["</s>", "USER:", "ASSISTANT:", "\nUSER:", "\nASSISTANT:"]
                )
                caption = response["choices"][0]["message"]["content"].strip()
                caption = caption.replace("ASSISTANT:", "").replace("USER:", "").strip()
                return _clean_caption(caption)
            detected_model_type = getattr(self.model.config, "model_type", None) if hasattr(self.model, "config") else None
            is_florence2 = (self.model_type == "florence2" or detected_model_type == "florence2")
            is_llava = (detected_model_type == "llava" or "llava" in str(type(self.model)).lower())
            if is_florence2:
                inputs = self.processor(images=image, text="<describe>", return_tensors="pt").to(device)
                with torch.no_grad():
                    outputs = self.model.generate(**inputs, max_new_tokens=150, do_sample=True, temperature=0.7)
                caption = self.processor.decode(outputs[0], skip_special_tokens=True).replace("<describe>", "").strip()
            else:
                if is_llava:
                    conversation_prompt = f"USER: <image>\n{prompt_text}\nASSISTANT:"
                    inputs = self.processor(images=image, text=conversation_prompt, return_tensors="pt").to(device)
                else:
                    inputs = self.processor(images=image, text=prompt_text, return_tensors="pt").to(device)
                with torch.no_grad():
                    outputs = self.model.generate(**inputs, max_new_tokens=150, do_sample=True, temperature=0.7, top_p=0.9)
                caption = self.processor.decode(outputs[0], skip_special_tokens=True) if hasattr(self.processor, "decode") else self.processor.batch_decode(outputs, skip_special_tokens=True)[0]
                if "ASSISTANT:" in caption:
                    caption = caption.split("ASSISTANT:")[-1].strip()
                if "USER:" in caption:
                    caption = caption.split("USER:")[-1].strip()
            if prompt_text in caption:
                caption = caption.replace(prompt_text, "").strip()
            out = _clean_caption(caption) if caption else ""
            logger.debug("Vision description length: %d", len(out))
            return out
        except Exception as e:
            logger.exception("Vision inference error for %s: %s", image_path, e)
            return ""

    def generate_caption(
        self,
        image_path: Path,
        tags: list[str],
        user_prompt: str = ""
    ) -> str:
        """Generate natural language caption: WD14 tags -> JoyCaption vision -> Llama 3 final caption.
        
        If CAPTION_LLAMA_GGUF_PATH exists: get vision description from JoyCaption, then send
        tags + vision description to Llama 3 and return its output. Otherwise use single-model path.
        """
        use_llama = CAPTION_LLAMA_GGUF_PATH.exists() and CAPTION_LLAMA_GGUF_PATH.is_file()
        if use_llama:
            logger.info("Caption flow: WD14 tags (%d) -> JoyCaption vision -> Llama", len(tags))
            tag_string = ", ".join(tags) if tags else ""
            if tag_string:
                vision_prompt = (
                    "Describe what you see in this image in one or two sentences. "
                    "The image has been tagged as follows; your description must reflect these specifics using the same level of detail—do not soften or omit: "
                    f"{tag_string}."
                )
            else:
                vision_prompt = "Describe what you see in this image in one or two sentences."
            vision_desc = self._run_vision_inference(image_path, vision_prompt)
            return _llama_finalize_caption(tags, vision_desc, user_prompt)
        # Legacy single-model path
        logger.info("Caption flow: legacy single-model (JoyCaption with tags in prompt)")
        if self.model is None:
            self.load_model(model_type=self.model_type)
        if self.model is None:
            return _post_process_caption(", ".join(tags) if tags else "A photograph.")
        tag_string = ", ".join(tags)
        if user_prompt:
            prompt = f"{user_prompt} Write 1-2 full sentences only. Use these as reference (do not list them): {tag_string}"
        else:
            prompt = f"Write one or two short sentences describing this image. Use these as reference only (do not list them): {tag_string}"
        try:
            caption = self._run_vision_inference(image_path, prompt)
            out = caption if caption else f"A photograph featuring {', '.join(tags[:5])}."
            return _post_process_caption(out)
        except Exception as e:
            logger.exception("JoyCaption generation error: %s", e)
            return _post_process_caption(", ".join(tags) if tags else "A photograph.")

    def unload_vision_models(self) -> None:
        """Unload vision model and processor to free VRAM before loading Llama."""
        if self.model is not None:
            self.model = None
        if self.processor is not None:
            self.processor = None
        self.is_gguf = False
        self.vram_manager.joycaption_model = None
        self.vram_manager.joycaption_processor = None
        import gc
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()


# Global singleton instance
_captioner: Optional[JoyCaption] = None


def get_captioner() -> JoyCaption:
    """Get the global JoyCaption instance."""
    global _captioner
    if _captioner is None:
        _captioner = JoyCaption()
    return _captioner


def generate_caption(
    image_path: Path,
    tags: list[str],
    user_prompt: str = ""
) -> str:
    """Convenience function to generate a caption.
    
    Args:
        image_path: Path to image file
        tags: List of WD14 tags
        user_prompt: Optional user prompt
    
    Returns:
        Caption string
    """
    captioner = get_captioner()
    return captioner.generate_caption(image_path, tags, user_prompt)


def run_caption_batch_two_phase(
    paths: list,
    tag_threshold: float = 0.5,
    user_prompt: str = ""
) -> list:
    """Run captioning in two phases to avoid VRAM bottleneck: vision (tag + describe) for all, then unload vision and run Llama for all.
    
    Phase 1: Load vision models (WD14 + JoyCaption), tag and get vision description for each image, then unload vision models.
    Phase 2: Load Llama, turn (tags, vision_desc) into final caption for each image.
    
    Args:
        paths: List of Path to image files
        tag_threshold: WD14 tag threshold
        user_prompt: Optional user prompt for Llama
    
    Returns:
        List of (path, tags, caption) for each image
    """
    from core.ai.tagger import tag_image, get_tagger
    logger.info("Batch caption two-phase: %d images", len(paths))
    vram = get_vram_manager()
    vram.ensure_state(State.CAPTIONING)
    # Eager-load WD14 so we fail fast with a clear error instead of using empty tags for every image
    if get_tagger().load_model() is None:
        raise RuntimeError(
            "WD14 model failed to load. Check the log for 'Failed to load WD14 model' (e.g. network, ONNX, or HuggingFace). Cannot run batch captioning."
        )
    captioner = get_captioner()
    # Phase 1: tag + vision description for all images (vision prompt includes tags so VLM uses same specificity)
    phase1_results = []
    for i, path in enumerate(paths):
        logger.info("Phase 1: %d/%d %s", i + 1, len(paths), path.name)
        tags = tag_image(path, threshold=tag_threshold)
        tag_string = ", ".join(tags) if tags else ""
        if tag_string:
            vision_prompt = (
                "Describe what you see in this image in one or two sentences. "
                "The image has been tagged as follows; your description must reflect these specifics using the same level of detail—do not soften or omit: "
                f"{tag_string}."
            )
        else:
            vision_prompt = "Describe what you see in this image in one or two sentences."
        vision_desc = captioner._run_vision_inference(path, vision_prompt)
        phase1_results.append((path, tags, vision_desc))
        logger.debug("  tags=%d, vision_desc len=%d", len(tags), len(vision_desc or ""))
    logger.info("Phase 1 done; unloading vision models")
    captioner.unload_vision_models()
    get_tagger().unload_model()
    vram.unload_captioning_models()
    # Phase 2: Llama finalizes each (tags, vision_desc) -> caption
    out = []
    for i, (path, tags, vision_desc) in enumerate(phase1_results):
        logger.info("Phase 2: %d/%d %s", i + 1, len(phase1_results), path.name)
        caption = _llama_finalize_caption(tags, vision_desc, user_prompt)
        out.append((path, tags, caption))
    logger.info("Batch caption complete: %d captions", len(out))
    return out
