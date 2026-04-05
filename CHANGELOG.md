# Changelog

All notable changes to LoRA Dataset Creator are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased] — 2026-04-05

### Fixed

- **TypeError when switching tabs** — `CTkTabview`'s command callback passes no
  arguments, but `_on_tab_changed` expected a `tab_name` parameter. Fixed by
  removing the parameter and reading the active tab via `self.tabview.get()`.

- **WinError 32 when saving with "No crop"** — PIL lazy-loads images and keeps the
  OS file handle open, causing a Windows sharing violation when `shutil.copy2`
  tried to copy the same file. Fixed by calling `image.load()` immediately after
  `Image.open()` to force PIL to read the data into memory and release the handle.

- **`KeyError` on `BUCKETS["no_crop"]`** — `calculate_crop_box` looked up the bucket
  name in the `BUCKETS` dict, which has no entry for `"no_crop"`. The call is now
  guarded; when `no_crop` is selected the full image bounds are used as crop coords.

- **Crop overlay not clearing when "No crop" selected** — The canvas still showed
  the yellow crop rectangle after switching to No crop. The display now branches:
  when `no_crop` is active the canvas shows a plain scaled image with no darkening
  or handles, and the crop info label reads the native resolution instead.

- **Crop box squashes when switching bucket** — Switching portrait/square/landscape
  radio buttons distorted the yellow crop rectangle because X and Y boundary clamping
  were done independently, breaking the target aspect ratio. The clamping logic in
  `calculate_crop_box` now scales the crop box proportionally to fit the image before
  centering, so the aspect ratio is always preserved.

- **YOLO re-ran on every radio button click** — Switching the bucket previously
  re-triggered the full YOLO person detection pipeline. The detected person is now
  cached on `SortTab` and `on_bucket_change` calls `calculate_crop_box` directly,
  making bucket switching instant.

### Added

- **Auto-detect portrait/landscape/square from image dimensions** — Each image's own
  aspect ratio now determines the default bucket selection when it loads, instead of
  always defaulting to square. YOLO person detection still overrides this when
  "Auto bucket" is enabled and a person is found.

- **"No crop (pass through)" option** — A new radio button in the Crop & Sort bucket
  panel. When selected, clicking Save & Next copies the original file to the output
  folder at its native resolution without any crop or resize, then adds it to the
  caption queue as normal.

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
