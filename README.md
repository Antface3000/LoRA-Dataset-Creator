# LoRA Dataset Manager

A modular, VRAM-aware desktop application for end-to-end preparation of AI image training datasets (specifically for Flux/SDXL LoRAs).

## Features

### Stage 1: Quality Gate (The "Critic")
- **Blur Detection**: Laplacian variance calculation
- **Aesthetic Scoring**: CLIP-based scoring (1-10 scale)
- **Score-Based Renaming**: Files renamed with `[Score]_Filename.ext` format
- **Interactive Thresholds**: Adjustable blur and aesthetic thresholds
- **Dry Run Mode**: Preview scores without moving files

### Stage 2: Aspect Ratio Bucketing & Smart Cropping
- **YOLOv8 Person Detection**: Automatically detects and centers on people
- **Smart Bucket Selection**: Auto-selects portrait/square/landscape based on person aspect ratio
- **Manual Override**: Drag to adjust crop position
- **Flux-Optimized Resolutions**: 
  - Portrait: 832x1216
  - Square: 1024x1024
  - Landscape: 1216x832

### Stage 3: The "Gold Standard" Captioning
- **WD14 Tagging**: Generates raw tags (e.g., '1girl', 'solo', 'denim_jacket')
- **JoyCaption VLM**: Generates natural language captions guided by tags
- **Glass Box Editor**: Dual-pane interface showing tags and captions side-by-side
- **Tag Management**: Add/remove tags with automatic re-generation
- **Dirty Flag**: Prevents auto-overwrite of manually edited captions

## Architecture

### Modular Design
- **`/core`**: Business logic only (NO UI code)
  - `/ai`: AI inference modules (aesthetic, cropper, tagger, captioner, vram)
  - `/data`: File handling and profiles
- **`/ui`**: View components only (delegates to core)
  - `/components`: Reusable widgets (ImageCard, TagChip)
  - `/tabs`: Tab interfaces (SortTab, EditorTab)

### VRAM Management
- **State Machine**: IDLE → CROPPING → CAPTIONING
- **Automatic Model Loading/Unloading**: Models unload when switching tabs
- **12GB VRAM Target**: Optimized for RTX 4070

## Installation

1. Install Python 3.10+
2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

Run the application:
```bash
python main.py
```

### Workflow

1. **Select Folders**: Choose source and output folders
2. **Quality Filter** (Optional): Run quality gate to filter/reject low-quality images
3. **Sort & Crop**: 
   - Images are automatically processed with person detection
   - Adjust crop manually if needed
   - Save to appropriate bucket folder
4. **Caption Editor**:
   - Load image
   - Generate tags (WD14)
   - Generate caption (JoyCaption)
   - Edit tags/caption as needed

## Profiles

Save different settings as profiles:
- **Flux Realistic**: Default profile for realistic images
- **SDXL Anime**: Profile optimized for anime-style images

Create custom profiles via the profile selector in the menu bar.

## Model Integration

### WD14 Tagger
To integrate WD14:
1. Place model files in appropriate location
2. Update `core/ai/tagger.py` `load_model()` method with actual model loading code

### JoyCaption VLM
To integrate JoyCaption:
1. Place model files in appropriate location (user will move model files)
2. Update `core/ai/captioner.py` `load_model()` method with actual model loading code

## Development Rules

- **File Size**: All files must be ≤250 lines
- **Path Handling**: Use `pathlib.Path` exclusively (NO `os.path`)
- **GUI Framework**: CustomTkinter only (NO tkinter in new code)
- **Separation**: NO UI code in `/core`, NO business logic in `/ui`
- **VRAM Safety**: Models must unload before state transitions

## Project Structure

```
/LoraDatasetManager
├── /core                   # NO UI CODE
│   ├── /ai                 # AI Logic
│   │   ├── aesthetic.py
│   │   ├── cropper.py
│   │   ├── tagger.py
│   │   ├── captioner.py
│   │   └── vram.py
│   ├── /data
│   │   ├── file_handler.py
│   │   └── profiles.py
│   ├── config.py
│   └── pipeline_manager.py
├── /ui                     # VIEW COMPONENTS ONLY
│   ├── /components
│   ├── /tabs
│   └── app_main.py
├── main.py
└── requirements.txt
```

## Philosophy: "The Glass Box"

- **Transparency**: See exactly why AI made decisions
- **Non-Destructive**: Original images never overwritten
- **VRAM Awareness**: Aggressive resource management for 12GB limit
