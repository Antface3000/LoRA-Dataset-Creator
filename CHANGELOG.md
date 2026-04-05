# Changelog

All notable changes to LoRA Dataset Creator are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [v0.2.0] — 2026-03-31

### Fixed

- **Caption truncation** — All local model generation limits raised from 150 tokens to 512
  (`max_new_tokens` for JoyCaption / Florence2 / Gemma3, `max_tokens` for GGUF finalization).
  Captions now produce full paragraphs instead of being cut off mid-sentence.

- **Caption edits reverting on image switch** — Clicking a different image in the Step 3
  list previously discarded any unsaved edits to tags and captions without warning.
  Edits are now saved automatically before switching. A **Save edits** button with visual
  confirmation ("Saved!") has also been added to the toolbar.

- **Crop & Sort images not flowing into the Wizard** — After cropping images in the
  Crop & Sort tab the app reported them as "added to the captioning queue" but the user
  still had to manually browse to the output folder in Wizard Step 2. Cropped images
  are now automatically imported into the session when navigating to Step 2, with
  duplicate detection so nothing is added twice.

---

## [v0.1.0] — 2026-03-30

### Added

- **Caption API backends** — Five captioning sources selectable per-profile in Settings:
  local HuggingFace models (JoyCaption, Florence2, Gemma3), Ollama local server,
  OpenAI (GPT-4o), Anthropic (Claude), and Google Gemini. Each backend has a
  dedicated settings panel with API key entry, model selection, a "Fetch models"
  button for Ollama, and a "Test connection" button that fires a live test request.

- **Simple rename mode** — Batch Rename tab now supports renaming images to a fixed
  base name with an optional sequential suffix (`character_name_001.jpg`, etc.).
  Configurable start number and zero-padding width.

- **Profile CRUD** — Full create / rename / duplicate / delete profile management via
  a new "Manage…" dialog accessible from the profile dropdown.

- **In-app tutorial** — A full getting-started guide accessible via the **?** button,
  covering the complete workflow, model setup (paths + download commands), caption
  API backends, and tips & troubleshooting.

- **Zoom / pan preview** — Image previews in Wizard Step 2, Step 3, and pop-out
  windows support mouse-wheel zoom and click-drag panning for close inspection.

- **Side-by-side tag/caption editors** — Step 3 shows tags and captions in resizable
  panels with a live image preview for easy comparison.

- **Tooltips** — Every interactive element across the entire application has a tooltip.

- **Batch rename (WD14), Crop & Sort, Wizard** tab order (previously Wizard first).

- **"Previous image" button** in Crop & Sort for stepping back through the queue.

- **Docs folder** — All developer documentation and loose markdown files moved to
  `docs/`. Model weights moved to `models/`.

- **README** — Comprehensive installation guide, AI models table, usage workflow,
  Caption API Backends section with per-backend install instructions and API key links.

- **`.gitignore`** — Excludes model weights, `flux_prep_config.json`, Python cache,
  and benchmark output.

### Fixed

- Settings button navigated to Finalize screen regardless of current wizard step.
- `_tkinter.TclError` from mixed `pack`/`grid` geometry managers in Step 2 preview.
- Crop & Sort images appearing squeezed/stretched due to canvas size fallback and
  image anchor mismatch.
- Wizard tab always landing on the last-visited step instead of Step 1 (Directories).
