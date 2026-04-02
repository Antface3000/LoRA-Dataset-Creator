# Project Evaluation: Current State vs. Cursor Rules

## Executive Summary

The current project is a **prototype/early-stage implementation** that implements **Stage 2 (Cropping)** functionality but is missing the modular architecture, VRAM management, and **Stage 1 (Quality Gate)** and **Stage 3 (Captioning)** features specified in `cursorrules.md`.

**Compliance Score: ~35%**

---

## 1. Architecture & Directory Structure

### ❌ **CRITICAL: Not Compliant**

**Specification:**
```
/LoraDatasetManager
├── /core                   # NO UI CODE ALLOWED HERE
│   ├── /ai                 # Heavy AI Logic
│   ├── /data
│   └── pipeline_manager.py
├── /ui                     # VIEW COMPONENTS ONLY
│   ├── /components
│   ├── /tabs
│   └── app_main.py
└── /assets
```

**Current State:**
- ❌ Flat file structure (all files in root)
- ❌ No `/core` directory
- ❌ No `/ui` directory
- ❌ No `/assets` directory
- ❌ Monolithic files (flux_dataset_prep.py = 2111 lines, flux_cropper.py = 974 lines)
- ❌ UI code mixed with business logic throughout

**Required Action:** Complete restructure into modular architecture.

---

## 2. File Size Constraints

### ❌ **CRITICAL: Not Compliant**

**Specification:** Files must not exceed ~250 lines.

**Current State:**
- `flux_dataset_prep.py`: **2111 lines** (8.4x over limit)
- `flux_cropper.py`: **974 lines** (3.9x over limit)
- `flux_lora_prep.py`: **997 lines** (4.0x over limit)
- `image_cropper.py`: **382 lines** (1.5x over limit)
- `batch_crop_flux.py`: **204 lines** (within limit ✓)

**Required Action:** Break down all files into modules per specification.

---

## 3. Tech Stack Compliance

### ✅ **Partially Compliant**

| Technology | Spec | Current | Status |
|------------|------|---------|--------|
| Python 3.10+ | ✅ | ✅ | ✅ Compliant |
| CustomTkinter | ✅ Strict | ⚠️ Mixed (tkinter + ctk) | ⚠️ Partial |
| Pillow (PIL) | ✅ | ✅ | ✅ Compliant |
| OpenCV (cv2) | ✅ Blur only | ✅ Used correctly | ✅ Compliant |
| torch + transformers | ✅ | ✅ Present | ✅ Compliant |
| ultralytics (YOLOv8) | ✅ | ✅ Present | ✅ Compliant |
| pathlib.Path | ✅ No os.path | ⚠️ Mixed usage | ⚠️ Partial |

**Issues:**
- `flux_dataset_prep.py` uses CustomTkinter ✅
- `flux_cropper.py` uses CustomTkinter ✅
- `flux_lora_prep.py` uses tkinter ❌
- `image_cropper.py` uses tkinter ❌
- **62 instances of `os.path`** found (should be `pathlib.Path`)

---

## 4. Pipeline Stages

### Stage 1: Ingestion & Quality Gate (The "Critic")

#### ⚠️ **Partially Implemented**

**Specification:**
- Blur Check (Laplacian Variance < 100)
- Aesthetic Score (CLIP, 1-10 scale)
- Move low scores to `/rejects`
- Rename files with `[Score]_Filename.ext`
- UI: Threshold slider + "Dry Run" mode

**Current State:**
- ✅ Blur detection implemented (`check_image_blur()`)
- ✅ Aesthetic scoring implemented (`check_image_aesthetic()`)
- ✅ Batch quality filter (`run_batch_quality_filter()`)
- ✅ Calibration mode (`run_calibration_mode()`)
- ⚠️ Files moved to `/blurry` or `/rejects` (not renamed with score prefix)
- ❌ No threshold slider in UI
- ⚠️ Dry run mode exists but is hardcoded (`DRY_RUN = False`)

**Gap:** Missing score-based file renaming and interactive threshold controls.

---

### Stage 2: Aspect Ratio Bucketing & Smart Cropping

#### ✅ **Fully Implemented**

**Specification:**
- Square: 1024x1024
- Portrait: 832x1216
- Landscape: 1216x832
- YOLOv8 person detection
- Center crop on person, fallback to center
- LANCZOS resampling
- Manual "Pan & Zoom" override

**Current State:**
- ✅ All bucket resolutions correct
- ✅ YOLOv8 person detection working
- ✅ Auto-bucket selection based on person aspect ratio
- ✅ Manual crop adjustment with drag handles
- ✅ LANCZOS resampling used
- ✅ Manual override via drag/resize handles

**Status:** ✅ **Compliant** (best implemented feature)

---

### Stage 3: The "Gold Standard" Captioning

#### ❌ **NOT IMPLEMENTED**

**Specification:**
- WD14 Tagger (Step 1)
- JoyCaption VLM (Step 2)
- Dual-pane "Glass Box" Editor (Step 3)
  - Left: Editable Tag Chips
  - Right: Generated Caption Text
  - Tag removal → Re-trigger VLM (unless dirty)
  - Manual caption edit → Set dirty flag

**Current State:**
- ❌ No WD14 integration
- ❌ No JoyCaption integration
- ❌ No captioning UI
- ❌ No tag management
- ❌ No dual-pane editor

**Status:** ❌ **Missing entirely**

---

## 5. VRAM Management

### ❌ **NOT IMPLEMENTED**

**Specification:**
- Single-Model Residency (cannot hold YOLO + WD14 + JoyCaption simultaneously)
- State A: Sorting/Cropping (YOLO Loaded)
- State B: Captioning (WD14 + JoyCaption Loaded)
- State C: Idle (VRAM cleared)
- PipelineManager must call `unload_models()` before tab switches

**Current State:**
- ❌ No VRAM manager (`core/ai/vram.py` missing)
- ❌ No model unloading logic
- ❌ YOLO model loaded at startup and never unloaded
- ❌ No state management for model residency
- ❌ No PipelineManager

**Status:** ❌ **Critical missing feature**

---

## 6. UI/UX Guidelines

### ⚠️ **Partially Compliant**

**Specification:**
- Dual-pane editor (Tags + Captions side-by-side)
- Aesthetic score overlay on images
- "Dirty" caption visual indicator
- Profiles system (JSON)

**Current State:**
- ❌ No dual-pane editor (captioning not implemented)
- ❌ No aesthetic score overlay on images
- ❌ No dirty caption indicator
- ⚠️ Config file exists (`flux_prep_config.json`) but not a full "Profiles" system

**Status:** ⚠️ **Incomplete**

---

## 7. Development Rules

### ⚠️ **Partially Compliant**

| Rule | Spec | Current | Status |
|------|------|---------|--------|
| VRAM Safety | ✅ Required | ❌ Missing | ❌ |
| No Magic Strings | ✅ Required | ⚠️ Some constants, but folder names hardcoded | ⚠️ |
| Pillow-Native | ✅ Required | ✅ Compliant | ✅ |

**Issues:**
- Folder names (`Portrait`, `Landscape`, `Square`, `blurry`, `rejects`) are hardcoded strings
- Should be defined in config constants file

---

## 8. Code Quality Issues

### Critical Issues:

1. **Monolithic Files:** Largest file is 2111 lines (should be ≤250)
2. **Mixed Concerns:** UI, business logic, and AI inference all in same files
3. **os.path Usage:** 62 instances found (should use `pathlib.Path`)
4. **No Separation:** No clear boundary between `/core` and `/ui`
5. **Inconsistent GUI:** Mix of tkinter and CustomTkinter
6. **No VRAM Management:** Models loaded indefinitely
7. **Missing Features:** Stage 3 (Captioning) completely absent

---

## 9. What's Working Well

✅ **Stage 2 (Cropping) is well-implemented:**
- YOLOv8 person detection
- Smart bucket selection
- Manual crop adjustment
- Proper aspect ratio handling
- LANCZOS resampling

✅ **Quality filtering foundation exists:**
- Blur detection
- Aesthetic scoring (CLIP)
- Batch processing capability

✅ **CustomTkinter integration** (in main files)

---

## 10. Migration Path Recommendations

### Phase 1: Restructure (High Priority)
1. Create `/core`, `/ui`, `/assets` directories
2. Split monolithic files into modules:
   - `core/ai/cropper.py` (YOLO logic)
   - `core/ai/aesthetic.py` (CLIP scoring)
   - `core/data/file_handler.py` (file I/O)
   - `ui/tabs/tab_sort.py` (cropping interface)
   - `ui/app_main.py` (main window)
3. Replace all `os.path` with `pathlib.Path`
4. Enforce CustomTkinter-only (remove tkinter usage)

### Phase 2: VRAM Management (Critical)
1. Create `core/ai/vram.py` (model manager)
2. Implement state-based model loading/unloading
3. Add `PipelineManager` to orchestrate states
4. Integrate with tab switching

### Phase 3: Complete Stage 1 (Medium Priority)
1. Add score-based file renaming (`[Score]_Filename.ext`)
2. Add threshold slider UI
3. Make dry-run mode interactive

### Phase 4: Implement Stage 3 (High Priority)
1. Integrate WD14 Tagger
2. Integrate JoyCaption VLM
3. Build dual-pane caption editor
4. Implement tag management and dirty flag system

### Phase 5: Polish (Low Priority)
1. Add aesthetic score overlay on images
2. Implement full Profiles system
3. Add visual indicators for dirty captions
4. Move all magic strings to config constants

---

## Summary

**Current State:** Functional prototype with Stage 2 (Cropping) working well, but missing:
- Modular architecture
- VRAM management
- Stage 3 (Captioning)
- Complete Stage 1 features
- Code organization compliance

**Priority Actions:**
1. **Restructure codebase** into modular architecture
2. **Implement VRAM management** (critical for 12GB limit)
3. **Complete Stage 3** (captioning system)
4. **Fix pathlib.Path usage** (62 instances)
5. **Standardize on CustomTkinter**

**Estimated Effort:** Significant refactoring required (~60-70% of codebase needs restructuring)
