# AI_CONTEXT.md
## 1. Project Overview & Philosophy

**Project Name:** LoRA Dataset Manager  
**Role:** Senior Software Architect & AI Engineer  
**Goal:** Create a local, high-performance desktop application for end-to-end preparation of AI image training datasets (specifically for Flux/SDXL LoRAs).

### Core Philosophy: "The Glass Box"

- **Transparency:** The user must see exactly why the AI made a decision (e.g., why a crop was chosen, which tags generated a caption).
- **Non-Destructive:** Original images are never overwritten. All operations create copies or metadata sidecars until final export.
- **VRAM Awareness:** The application targets a 12GB VRAM (RTX 4070) limit. It must aggressively manage resources by loading/unloading models (YOLO vs. JoyCaption vs. WD14) to prevent OOM errors.

## 2. Tech Stack & Hard Constraints

### Core Technologies

- **Language:** Python 3.10+
- **GUI Framework:** CustomTkinter (Strict enforcement. Modern look, compatible with previous "vibe" scripts).
- **Image Processing:** Pillow (PIL) for all resizing, cropping, and format conversion. OpenCV (cv2) only for blur detection.
- **AI Inference:** torch + transformers.
- **Object Detection:** ultralytics (YOLOv8n) for smart cropping.
- **Path Handling:** pathlib.Path (No os.path strings allowed).

### Hardware Constraints

- **Primary Target:** NVIDIA RTX 4070 (12GB VRAM).
- **Concurrency:** Single-Model Residency. The app cannot hold YOLO, WD14, and JoyCaption in VRAM simultaneously.
  - **State A:** Sorting/Cropping (YOLO Loaded).
  - **State B:** Captioning (WD14 + JoyCaption Loaded).
  - **State C:** Idle (VRAM cleared).

## 3. Directory Structure (Anti-Monolith)

Code must be modular. Files must not exceed ~250 lines.

```
/LoraDatasetManager
│
├── /core                   # NO UI CODE ALLOWED HERE
│   ├── /ai                 # Heavy AI Logic
│   │   ├── aesthetic.py    # CLIP scoring & Laplacian Blur
│   │   ├── cropper.py      # YOLOv8 logic & Aspect Ratio math
│   │   ├── tagger.py       # WD14 inference
│   │   ├── captioner.py    # JoyCaption/LLM inference
│   │   └── vram.py         # Global VRAM manager/garbage collection
│   ├── /data
│   │   ├── file_handler.py # File I/O, Moving, Renaming
│   │   └── profiles.py     # Saving/Loading user settings
│   └── pipeline_manager.py # Orchestrates the flow between modules
│
├── /ui                     # VIEW COMPONENTS ONLY
│   ├── /components         # Reusable widgets (ImageCard, TagChip)
│   ├── /tabs
│   │   ├── tab_sort.py     # Filter/Sort/Crop Interface
│   │   └── tab_editor.py   # The "Glass Box" Caption Editor
│   └── app_main.py         # Main Window & Entry Point
│
├── /assets                 # Icons, themes
├── AI_CONTEXT.md           # This file (Source of Truth)
└── requirements.txt
```

## 4. Pipeline Specifications

### Stage 1: Ingestion & Quality Gate (The "Critic")

- **Objective:** Filter out "trash" data before processing.
- **Logic:**
  - **Blur Check:** Calculate Laplacian Variance. If < 100 (configurable), flag as Blurry.
  - **Aesthetic Score:** Load clip-vit-large-patch14 (or compatible linear probe). Generate score (1-10).
  - **Action:**
    - Score < MIN_AESTHETIC_SCORE: Move to /rejects.
    - Score > Threshold: Rename file to [Score]_Filename.ext and proceed.
- **UI:** User sets threshold via slider. "Dry Run" mode prints scores without moving files.

### Stage 2: Aspect Ratio Bucketing & Smart Cropping

- **Objective:** Sort images by shape and maximize subject retention.
- **Bucketing Logic:**
  - **Square:** Width == Height → Target: 1024x1024
  - **Portrait:** Height > Width → Target: 832x1216 (Flux magic number)
  - **Landscape:** Width > Height → Target: 1216x832 (Flux magic number)
- **Cropping Logic (YOLOv8):**
  - Detect class `person`.
  - If found: Calculate crop box centered on the largest person.
  - If not found: Fallback to Center Crop.
  - **Resampling:** Strictly use Image.Resampling.LANCZOS.
- **UI Integration:** "Pan & Zoom" Manual Override. If the user dislikes the auto-crop, they can manually reposition the image in the viewport.

### Stage 3: The "Gold Standard" Captioning

- **Architecture:** Tag-Guided VLM.
- **Step 1 (WD14):**
  - Run WD14 Tagger.
  - Output: List of raw tags (e.g., 1girl, solo, denim_jacket, outdoors).
  - Constraint: Tags are the "Source of Truth."
- **Step 2 (JoyCaption VLM):**
  - Input: Image + WD14 Tags + User Prompt.
  - Process: VLM generates natural language description strictly guided by the provided tags.
- **Step 3 (The "Glass Box" Editor):**
  - **Left Pane:** Editable Tag Chips (Remove/Add tags).
  - **Right Pane:** Generated Caption Text.
  - **Interaction:**
    - Removing a tag in Left Pane → Re-triggers VLM generation (unless "Dirty").
    - Manually editing Right Pane → Sets Dirty_Flag = True (Prevents auto-overwrite).

## 5. UI/UX Guidelines

- **Dual-Pane Editor:** The captioning tab must show Tags and Captions side-by-side.
- **Visual Feedback:**
  - Images in the "Sorter" view should show their Aesthetic Score overlay in the corner.
  - "Dirty" captions should have a visual indicator (e.g., modified color border).
- **Profiles:**
  - All settings (Crop Resolution, VLM Prompts, Thresholds) must be savable as JSON "Profiles."
  - Example: "Profile: Flux Realistic" vs "Profile: SDXL Anime."

## 6. Development Rules

- **VRAM Safety:** Before switching tabs (e.g., from Sorting to Captioning), the PipelineManager must explicitly call `unload_models()` to clear the GPU.
- **No Magic Strings:** All folder names (portrait, landscape, rejects) and resolutions must be defined as constants in a config file.
- **Pillow-Native:** Do not convert to cv2 format unless absolutely necessary for the Laplacian check. Keep pipeline in PIL.Image to preserve metadata/color profiles.
