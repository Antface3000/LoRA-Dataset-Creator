"""Core configuration constants - No magic strings allowed."""

from pathlib import Path

# Bucket resolutions (width, height) for Flux/SDXL LoRA training
BUCKET_PORTRAIT = (832, 1216)
BUCKET_SQUARE = (1024, 1024)
BUCKET_LANDSCAPE = (1216, 832)

# Bucket name mappings
BUCKETS = {
    'portrait': BUCKET_PORTRAIT,
    'square': BUCKET_SQUARE,
    'landscape': BUCKET_LANDSCAPE,
}

# Folder names for output organization
FOLDER_PORTRAIT = "Portrait"
FOLDER_LANDSCAPE = "Landscape"
FOLDER_SQUARE = "Square"
FOLDER_REJECTS = "rejects"
FOLDER_BLURRY = "blurry"
FOLDER_PROCESSED = "processed"

# Folder name mappings
FOLDERS = {
    'portrait': FOLDER_PORTRAIT,
    'landscape': FOLDER_LANDSCAPE,
    'square': FOLDER_SQUARE,
}

# Quality filter thresholds
MIN_LAPLACIAN_VARIANCE = 100.0  # Images below this are considered blurry
MIN_AESTHETIC_SCORE = 5.0  # Images below this (1-10 scale) are rejected

# Valid image file extensions
VALID_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}

# YOLO person detection class ID
YOLO_PERSON_CLASS = 0

# Default padding margin for person-centered crops
DEFAULT_PADDING_MARGIN = 10

# Default confidence threshold for person detection
DEFAULT_PERSON_CONFIDENCE = 0.15

# Image resampling method (must be LANCZOS per spec)
RESAMPLING_METHOD = "LANCZOS"  # Maps to Image.Resampling.LANCZOS

# Model paths - relative to project root
MODELS_DIR = Path(__file__).parent.parent / "models"
JOYCAPTION_MODEL_PATH = MODELS_DIR / "joycaption"
GEMMA3_MODEL_PATH = MODELS_DIR / "gemma3"
FLORENCE2_MODEL_PATH = MODELS_DIR / "florence2"
WD14_MODEL_NAME = "SmilingWolf/wd-v1-4-vit-tagger-v2"  # HuggingFace model name or local path

# Caption pipeline: Wizard-Vicuna 7B Uncensored (GGUF) turns tags + vision description into final caption
CAPTION_LLAMA_GGUF_PATH = MODELS_DIR / "Wizard_Vicuna" / "Wizard-Vicuna-7B-Uncensored.Q4_K_M.gguf"

# Ollama model paths (Windows default locations)
# Ollama typically stores models at: %USERPROFILE%\.ollama\models or C:\Users\<username>\.ollama\models
import os
OLLAMA_BASE_DIR = Path(os.path.expanduser("~")) / ".ollama" / "models"
# Common Ollama Gemma3 model names: "gemma2:latest", "gemma:latest", etc.
# You can set a custom path here if Ollama is installed elsewhere
GEMMA3_OLLAMA_PATH = None  # Set to Path("C:/path/to/ollama/models/gemma3") if needed

# Caption VLM system prompt (GGUF LLaVA / JoyCaption). Empty string = use model default.
# Tags are the source of truth; describe using the same specificity—no euphemisms or omissions.
CAPTION_SYSTEM_PROMPT = (
    "You are an image captioning expert for LoRA training data. "
    "Output 1-3 full sentences of natural language. Do not output comma-separated word lists or a line starting with 'Tags:'. "
    "The tags you are given are the source of truth: describe exactly what they indicate using the same wording and specificity. "
    "Do not omit any tagged concept. Do not replace any tag with a euphemism or vaguer term (e.g. do not say 'genital area' if the tag is more specific). "
    "Write coherent prose that incorporates every tag at the same level of detail."
)

# Caption post-processing: find/replace (applied in order) and trigger words (appended to caption for LoRA)
# Format: list of (find_string, replace_string). Example: ("small to medium sized", "small")
CAPTION_FIND_REPLACE = [
    ("small to medium sized", "small"),
]
# Trigger words appended to the end of the caption (e.g. LoRA activation token). Leave empty for none.
CAPTION_TRIGGER_WORDS = ""
