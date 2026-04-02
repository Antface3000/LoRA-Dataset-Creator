# Model Setup Guide

## Where to Place Models

### JoyCaption Model
Place your JoyCaption model files in:
```
models/joycaption/
```

### Gemma3 Model
Place your Gemma3 model files in:
```
models/gemma3/
```

### Florence2 Model
Place your Florence2 model files in:
```
models/florence2/
```

## Model Format

Models should be in **HuggingFace format**, which typically includes:
- `config.json` - Model configuration
- `pytorch_model.bin` or `model.safetensors` - Model weights
- `tokenizer.json` or `tokenizer_config.json` - Tokenizer files
- `preprocessor_config.json` - Image preprocessing config (for vision models)
- Other supporting files as needed

## Quick Setup Steps

1. **Create the directories** (already done):
   - `models/joycaption/`
   - `models/gemma3/`
   - `models/florence2/`

2. **Copy your model files**:
   - Copy all JoyCaption model files into `models/joycaption/`
   - Copy all Gemma3 model files into `models/gemma3/`
   - Copy all Florence2 model files into `models/florence2/`

3. **Verify structure**:
   ```
   models/
   ├── joycaption/
   │   ├── config.json
   │   ├── pytorch_model.bin (or model.safetensors)
   │   ├── tokenizer.json
   │   └── ... (other files)
   ├── gemma3/
   │   ├── config.json
   │   ├── pytorch_model.bin (or model.safetensors)
   │   ├── tokenizer.json
   │   └── ... (other files)
   └── florence2/
       ├── config.json
       ├── pytorch_model.bin (or model.safetensors)
       ├── tokenizer.json
       └── ... (other files)
   ```

## Using the Models

The application will automatically:
- Detect models when you use the Caption Editor tab
- Load the appropriate model based on configuration
- Fall back to tag-based captions if models aren't found

## Switching Between Models

Currently, the code defaults to JoyCaption. To use a different model, modify `core/ai/captioner.py` line 20:

```python
self.model_type = "joycaption"  # Options: "joycaption", "gemma3", or "florence2"
```

Change to:
- `"gemma3"` to use Gemma3
- `"florence2"` to use Florence2
- `"joycaption"` to use JoyCaption (default)

Or we can add a UI option to switch between models in the future.

## Troubleshooting

- **Model not found**: Ensure all model files are in the correct directory
- **Out of memory**: Models are large - ensure you have enough VRAM (12GB+ recommended)
- **Loading errors**: Check that model files are complete and in HuggingFace format
