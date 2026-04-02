# Models Directory

Place your AI model files in the appropriate subdirectories:

## Directory Structure

```
models/
├── joycaption/     # JoyCaption VLM model files
├── gemma3/         # Gemma3 model files (alternative to JoyCaption)
├── florence2/      # Florence2 vision-language model files
└── README.md       # This file
```

## Model Formats

Models should be in HuggingFace format (containing `config.json`, `pytorch_model.bin` or `.safetensors`, `tokenizer.json`, etc.).

### JoyCaption Model
Place your JoyCaption model files in: `models/joycaption/`

The directory should contain files like:
- `config.json`
- `pytorch_model.bin` or `model.safetensors`
- `tokenizer.json` or `tokenizer_config.json`
- `preprocessor_config.json` (if applicable)
- Any other model files

### Gemma3 Model
Place your Gemma3 model files in: `models/gemma3/`

The directory should contain files like:
- `config.json`
- `pytorch_model.bin` or `model.safetensors`
- `tokenizer.json` or `tokenizer_config.json`
- Any other model files

### Florence2 Model
Place your Florence2 model files in: `models/florence2/`

The directory should contain files like:
- `config.json`
- `pytorch_model.bin` or `model.safetensors`
- `tokenizer.json` or `tokenizer_config.json`
- `preprocessor_config.json` (for vision models)
- Any other model files

## Usage

The application will automatically detect and load models from these directories when you use the Caption Editor tab.

If a model is not found, the application will fall back to tag-based captions.

## Notes

- Models are loaded on-demand when you first use the Caption Editor
- Models are automatically unloaded when switching to other tabs (VRAM management)
- Ensure you have enough VRAM (12GB recommended for RTX 4070)
