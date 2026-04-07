# LoRA Dataset Creator

A desktop application for end-to-end preparation of AI image training datasets for Flux/SDXL LoRAs.
Handles the full pipeline: crop, tag, caption, and finalize — all in one place.

## Features

- **Crop & Sort** — Manual or YOLO-automated cropping into portrait / square / landscape buckets
- **Quality Filter** — Blur detection and aesthetic scoring to remove low-quality images
- **WD14 Tagging** — Automatic tag generation with adjustable confidence threshold
- **VLM Captioning** — Natural language captions via JoyCaption, Florence2, or Gemma3
- **Caption Finalization** — Optional GGUF LLM pass to polish raw captions into coherent prose
- **Batch Rename** — Rename images using WD14 tags as filename prefixes
- **Profile System** — Save folder paths, trigger words, and caption settings per project
- **Built-in Tutorial** — Click the **?** button in the app for a full getting-started guide

---

## Prerequisites

Before installing, make sure you have:

1. **Python 3.10 or newer** — [python.org/downloads](https://www.python.org/downloads/)
   - During install, tick **"Add Python to PATH"**
2. **Git** — [git-scm.com/download/win](https://git-scm.com/download/win)
3. **NVIDIA GPU with CUDA** recommended (8 GB+ VRAM for captioning). CPU-only works for tagging.

---

## Installation

Open **PowerShell** (press **Win + R**, type `powershell`, press **Enter**) and run the following commands one at a time:

```powershell
git clone https://github.com/Antface3000/LoRA-Dataset-Creator.git
cd LoRA-Dataset-Creator
pip install -r requirements.txt
python main.py
```

The app will launch. No AI models are required to start — download only what you need (see [AI Models](#ai-models)).

### Optional — Caption API backend packages

`requirements.txt` covers local model captioning. If you plan to use a remote or Ollama backend, install the matching package **after** the step above:

| Backend | Install command |
|---|---|
| Ollama (local server) | `pip install requests` |
| OpenAI (GPT-4o, etc.) | `pip install openai` |
| Anthropic (Claude) | `pip install anthropic` |
| Google Gemini | `pip install google-genai` |

You can install any of these at any time — the app will show an error message if a required package is missing when you test the connection. Full setup instructions for each backend are in [Caption API Backends](#caption-api-backends) below.

---

## AI Models

All models go in the `models/` folder. The app works without them for basic file management;
models are only needed for tagging, captioning, and auto-cropping.

| Model | Required for | Path | Download |
|---|---|---|---|
| YOLOv8n | Auto crop | `models/yolov8n.pt` | [Ultralytics releases](https://github.com/ultralytics/assets/releases) |
| WD14 Tagger | Generate tags | *(auto-downloaded on first use)* | Automatic |
| JoyCaption | Generate captions | `models/joycaption/` | HuggingFace `fancyfeast/llama-joycaption-alpha-two-hf-llava` |
| Florence2 | Generate captions | `models/florence2/` | HuggingFace `microsoft/Florence-2-large` |
| Gemma3 | Generate captions | `models/gemma3/` | HuggingFace `google/gemma-3-4b-it` *(requires HF login)* |
| Wizard-Vicuna GGUF | Caption finalization | `models/Wizard_Vicuna/Wizard-Vicuna-7B-Uncensored.Q4_K_M.gguf` | HuggingFace `TheBloke/Wizard-Vicuna-7B-Uncensored-GGUF` |

**Download HuggingFace models with:**
```powershell
pip install huggingface_hub
huggingface-cli download fancyfeast/llama-joycaption-alpha-two-hf-llava --local-dir models/joycaption
```

See `models/README.md` or open the in-app tutorial (**?** button) for full instructions.

---

## Usage

```powershell
python main.py
```

### Typical workflow

1. **Wizard › Step 1** — Set your source and output folders
2. **Wizard › Step 2** — Add images to the session
3. **Crop & Sort tab** — Review and crop images (manual or auto with YOLO)
4. **Wizard › Step 3** — Generate tags and captions, edit as needed
5. **Wizard › Step 4** — Finalize: writes images + `.txt` sidecars to the output folder

The **Batch Rename** tab (optional) lets you rename raw images using WD14 tags before processing.

---

## Project Structure

```
LoRA-Dataset-Creator/
├── core/               # Business logic (no UI code)
│   ├── ai/             # AI modules: cropper, tagger, captioner, vram
│   ├── data/           # File handling and profile management
│   ├── config.py       # Model paths and constants
│   └── session.py      # In-memory session state
├── ui/                 # UI only (no business logic)
│   ├── wizard/         # Wizard steps
│   ├── tabs/           # Crop & Sort, Batch Rename, Caption Editor tabs
│   ├── app_main.py     # Main window
│   └── tutorial_dialog.py
├── models/             # AI model weights (not included — see above)
├── docs/               # Developer documentation
├── main.py
└── requirements.txt
```

---

## Caption API Backends

The app supports five captioning backends, selectable per-profile in **Settings → Caption Model / Backend**.

> **Before using a remote backend**, install its package (see the table in [Installation](#installation)) by running the `pip install` command in PowerShell from inside the `LoRA-Dataset-Creator` folder.

### `local` (default — no internet required)

Uses a locally installed HuggingFace transformers model on your GPU.  
Choose between **joycaption**, **florence2**, or **gemma3** in the *Local model* dropdown.  
See [AI Models](#ai-models) for download instructions. No extra pip package needed — covered by `requirements.txt`.

### `ollama` — local Ollama server

Runs vision-capable open-source models entirely on your machine (no API key, no cost).

**Requires:** `pip install requests` *(see [Installation](#installation))*

1. Install Ollama from <https://ollama.com/download>
2. Pull a vision model in PowerShell:
   ```powershell
   ollama pull llava
   ```
   Other options: `bakllava`, `moondream`, `llava-llama3`
3. The server starts automatically after install. You can also run `ollama serve` manually.
4. In the app: **Settings → Caption source = `ollama`**, set the URL to `http://localhost:11434`, enter the model name or click **Fetch models**.

### `openai` — OpenAI GPT-4o

**Requires:** `pip install openai` *(see [Installation](#installation))*

1. Create an API key at <https://platform.openai.com/api-keys>
2. In the app: **Settings → Caption source = `openai`**, paste your key, choose a model (default: `gpt-4o`).

Cost: ~$0.002–$0.005 per image with `gpt-4o`.

### `anthropic` — Anthropic Claude

**Requires:** `pip install anthropic` *(see [Installation](#installation))*

1. Create an API key at <https://console.anthropic.com>
2. In the app: **Settings → Caption source = `anthropic`**, paste your key, choose a model (default: `claude-3-5-haiku-20241022` — cheapest; `claude-3-5-sonnet` for best quality).

### `gemini` — Google Gemini

**Requires:** `pip install google-genai` *(see [Installation](#installation))*

> **Note:** The older `google-generativeai` package is no longer compatible. Use `google-genai` (the official Google Gen AI SDK).

Free tier: 15 requests/min, 1 500 requests/day (as of 2026).

1. Create an API key at <https://aistudio.google.com/app/apikey>
2. In the app: **Settings → Caption source = `gemini`**, paste your key, choose a model (default: `gemini-2.5-flash`).

---

## System Requirements

| Component | Minimum | Recommended |
|---|---|---|
| Python | 3.10 | 3.11+ |
| RAM | 8 GB | 16 GB |
| VRAM | 0 GB (CPU) | 8–12 GB (NVIDIA) |
| Storage | 2 GB | 20 GB (with all models) |
| OS | Windows 10 | Windows 11 |
