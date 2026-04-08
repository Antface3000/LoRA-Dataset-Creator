# Changelog

All notable changes to LoRA Dataset Creator are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased] — 2026-04-07

### Added

- **Caption prompt presets** — Wizard Step 3 and **Settings → Caption** include a preset
  row: built-in system prompts (*General descriptive*, *LoRA / full tag fidelity*, *Short /
  one sentence*), **Apply**, **Save current…** (names a preset), and **Delete saved**.
  User presets are stored in `flux_prep_config.json` under `caption_prompt_library`
  (`name`, `system`, `user`). New modules: `core/data/caption_prompt_presets.py`,
  `ui/caption_prompt_presets_ui.py`.

- **Session tag pool mode (Step 3)** — The lower tag list is labeled **Session tag pool**
  with a menu: **Scanned tags (WD14)** (default) shows the union of WD14 results only;
  **All session tags** includes manual tags too. Each `SessionItem` has
  `tags_from_scan` updated by WD14; manual adds use `tags` only. Preference is saved per
  profile as `master_tag_list_mode`.

- **Session tag pool filter & remove** — **Not on this image only** (per-profile
  `master_tag_pool_not_on_image_only`) limits the pool list to tags you have not added to
  the current image yet. Each pool row has **×** to remove that tag from every image in
  the session (with confirmation), clearing it from both `tags` and `tags_from_scan`.

### Changed

- **Wizard Step 3 toolbar** — One **general** bar under the hint (image index, Load, tag
  threshold, Stop when busy, Save edits, status, Output, trigger words, Export). **Generate
  tags** / **Batch tags** sit above the Tags column; **Generate caption** / **Batch
  caption** above the Caption column.

- **Master tag list filter** — The session pool lists up to the existing render cap
  without requiring a minimum filter length (removed the old “type N characters” gate).

- **Wizard preview performance** — Zoom/pan canvases downsample large images before
  display (`max_preview_side` / `max_photo_side`, stricter for Step 3 than Step 2, higher
  for “Preview in window”) and cap zoom so `PhotoImage` work stays bounded on the UI thread.

- **Step 3 session list selection** — Choosing another image updates the list highlight
  without loading the preview and rebuilding tag lists twice (`_refresh_list` with
  `refresh_editors=False` before loading editors).

- **Step 3 tag +/- responsiveness** — When the filter is empty, **Not on this image only**
  is off, and the master pool is under the render cap, toggling a tag rebuilds the
  current-image list only and patches the matching pool row in place instead of
  destroying both scroll frames every time.

- **Smart Crop batch resize** — After YOLO/NudeNet crop, images are fitted with
  `resize_cover_to_bucket` (`ImageOps.fit`: scale + center crop to bucket size) instead
  of letterboxing with black bars.

- **Local caption pipeline** — Vision-stage user text is built from WD14 tags; Llama
  finalization respects the Step 3 / profile system prompt via
  `_resolve_local_caption_system`. `_clean_caption` strips more model junk (encoding
  lines, empty `USER:`/`ASSISTANT:` markers, `__media__` echoes) and leading role prefixes.

- **Crop & Sort overlay** — Outside-crop dimming is drawn only in the four regions
  outside the crop rectangle so the crop interior stays full brightness. Resize handles
  are clamped so they are not half-clipped when the crop is flush with the image edge.

- **Google Gemini backend migrated to `google-genai`** — The `google-generativeai`
  package is deprecated and no longer compatible with the Gemini API. The backend now
  uses the official Google Gen AI SDK (`google-genai`). Update your environment:
  ```
  pip uninstall google-generativeai
  pip install google-genai
  ```
  The API call is now client-based (`genai.Client(api_key=…)`) and images are sent as
  JPEG bytes via `types.Part.from_bytes`, making the integration more robust.
  `requirements.txt`, the README, and the in-app tutorial have all been updated.

- **NudeNet toggle in Settings** — Body-part detection controls are now hidden by
  default. Enable them per-profile via **Settings → Smart Detection → Enable NudeNet
  body-part detection** (requires `pip install nudenet`). The setting is saved to each
  profile so different projects can have different preferences.

- **UI layout — top control bar** — The Crop & Sort top bar is split into two rows
  (folder buttons / quality sliders) so all controls are visible at the default window
  size without horizontal clipping.

- **Default window size** — Increased from 1000 × 800 to 1280 × 860 (minimum 1050 × 650)
  to accommodate the full control bar without requiring manual resizing.

- **Step indicator hidden on non-Wizard tabs** — The "Step X of 4 – …" label in the
  header is now only shown when the Wizard tab is active.

### Fixed

- **Default profile template** — New profiles include `master_tag_pool_not_on_image_only`
  in the factory defaults so the Step 3 pool filter preference saves consistently.

- **Session tag pool menu stuck or profile wiped** — Changing the pool mode no longer
  builds the save payload from `load_profile(...) or {}` (which could replace the whole
  profile if missing). Saves always shallow-copy `get_current_profile()`. Pool mode is
  tracked explicitly and the `CTkOptionMenu` is updated with `.set()` so the widget stays
  in sync with the profile after reloads.

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
