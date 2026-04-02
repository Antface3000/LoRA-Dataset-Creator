"""Tutorial / Getting-Started dialog for the LoRA Dataset Manager."""

import customtkinter as ctk


# ---------------------------------------------------------------------------
# Content definition — each section is (title, body_paragraphs)
# ---------------------------------------------------------------------------
_SECTIONS = [
    (
        "Overview — Building a LoRA Dataset",
        [
            "This tool guides you through five stages to turn a folder of raw images into "
            "a clean, tagged, and captioned dataset for training a LoRA model.",
            "Typical workflow:\n"
            "  1. Set Folders  →  2. Add Images  →  3. Crop & Sort  →  "
            "4. Tag & Caption  →  5. Finalize\n"
            "The Batch Rename tab is an optional pre-processing step.",
        ],
    ),
    (
        "Step 1 — Set Folders  (Wizard › Directories)",
        [
            "Open the Wizard tab and use Step 1 to point the tool at your images.",
            "• Source folder — the folder containing your raw, unprocessed images.\n"
            "• Output folder — where the final cropped and tagged images will be written.",
            "Click Browse… next to each field and choose the appropriate folder. "
            "The paths are saved to your active profile so they reload on the next launch.",
        ],
    ),
    (
        "Step 2 — Add Images  (Wizard › Images)",
        [
            "Click Next to reach Step 2, which builds the session list of images the "
            "wizard will process.",
            "• Add from source folder — loads every supported image (.jpg, .png, .webp) "
            "from the source folder you set in Step 1.\n"
            "• Add files… — pick individual files from anywhere on disk.\n"
            "• Remove — delete the selected image(s) from the session (files are not "
            "deleted from disk).\n"
            "• Rename… — change the output filename stem for a single image.\n"
            "• Add prefix / suffix to all — batch-rename the output stems.",
            "Click any row in the list to preview the image on the right. "
            "Scroll to zoom and drag to pan the preview.",
        ],
    ),
    (
        "Crop & Sort Tab  (dedicated tab)",
        [
            "The Crop & Sort tab lets you manually review and crop each image before "
            "tagging. Switch to it from the tab bar at the top.",
            "Getting started:\n"
            "  1. Click Select Source to choose the folder of raw images.\n"
            "  2. Click Select Output to choose where cropped images are saved.\n"
            "  3. The first image loads automatically.",
            "Cropping:\n"
            "  • Choose a bucket — Portrait (768×1152), Square (1024×1024), or "
            "Landscape (1152×768).\n"
            "  • Click and drag on the canvas to draw a crop rectangle.\n"
            "  • Save & Next crops and resizes to the selected bucket, then loads the "
            "next image.\n"
            "  • Skip moves to the next image without saving.\n"
            "  • ← Previous goes back one image (saved crops are not undone).",
            "Batch / automatic cropping:\n"
            "  • Auto crop all runs YOLO person detection on every image in the source "
            "folder and crops automatically to the chosen bucket.\n"
            "  • Quality Filter scores every image for blur (Laplacian variance) and "
            "aesthetic quality, and moves rejects to a subfolder. "
            "Enable Dry Run to preview which images would be rejected without moving "
            "any files.",
        ],
    ),
    (
        "Step 3 — Tag & Caption  (Wizard › Tags & Captions)",
        [
            "After adding images in Step 2, click Next to reach the tagging and "
            "captioning screen.",
            "Working with a single image:\n"
            "  1. Type an index number (1-based) in the Image index box and click Load.\n"
            "  2. Click Generate tags to run the WD14 tagger. Adjust the Tag threshold "
            "slider to control confidence — higher values produce fewer, more confident "
            "tags.\n"
            "  3. Click Generate caption to run the vision model (JoyCaption, Florence2, "
            "or Gemma3 depending on your config).\n"
            "  4. Edit the Tags and Caption fields directly — the text boxes are fully "
            "editable.\n"
            "  5. Set Trigger words to prepend a LoRA trigger token to every caption.",
            "Batch processing:\n"
            "  • Batch tags (all) — tag every image in the session in one pass.\n"
            "  • Batch caption (all) — caption every image. This can take several "
            "minutes depending on model and GPU.",
            "Output format controls what gets written to the .txt sidecar files:\n"
            "  • Tags only — comma-separated WD14 tags.\n"
            "  • Natural language — the generated caption.\n"
            "  • Both — tags prepended to the caption.",
            "The inline preview supports zoom (mouse wheel) and pan (click-drag). "
            "Click Preview in window to open a larger resizable pop-out.",
        ],
    ),
    (
        "Step 4 — Finalize  (Wizard › Finalize)",
        [
            "Click Next on Step 3 to reach the Finalize screen. Review the summary "
            "(image count, output path, processed path) before committing.",
            "Options:\n"
            "  • Move originals to processed — after writing output files, the source "
            "images are moved to a processed/ subfolder. Uncheck to copy instead "
            "(safer if you want to keep originals in place).\n"
            "  • Finalize workers — number of parallel threads for writing files. "
            "2 or 4 workers is faster on SSDs; keep at 1 for spinning disks.",
            "Click Finalize to:\n"
            "  1. Write each image to the output folder at the correct resolution.\n"
            "  2. Write a .txt sidecar file next to each image with the tags/caption.\n"
            "  3. Archive (move or copy) the originals to the processed/ folder.",
            "The output folder is now ready to use as a LoRA training dataset.",
        ],
    ),
    (
        "Batch Rename Tab  (optional pre-processing)",
        [
            "The Batch Rename tab lets you rename raw images using WD14 tags as "
            "filename prefixes before running the wizard. This is optional but can "
            "help keep your file library organised.",
            "Workflow:\n"
            "  1. Click Browse… and select the folder of images to rename.\n"
            "  2. Set Confidence threshold — tags below this score are ignored.\n"
            "  3. Set Max tags — how many tags to prepend (5–10).\n"
            "  4. (Optional) Enter Words to omit — tags you never want in filenames.\n"
            "  5. (Optional) Enter Prepend (manual) — fixed text always added first "
            "(e.g. your character name or style token).\n"
            "  6. Click Analyze (dry run) to preview proposed renames without touching "
            "any files.\n"
            "  7. Review the list, then click Apply renames to commit.",
            "Click Reset list at any time to clear proposals and adjust settings.",
        ],
    ),
    (
        "Model Setup — Where to Get and Place AI Models",
        [
            "All AI models live inside the models/ folder at the project root. "
            "The folder already exists and contains subdirectories for each model. "
            "You do not need every model — read the notes below to install only what you need.",
            "── Tagging (required for Generate tags / Batch tags) ──\n"
            "\n"
            "YOLOv8n  (person detection for Auto crop)\n"
            "  Path : models/yolov8n.pt\n"
            "  Download : https://github.com/ultralytics/assets/releases  (yolov8n.pt)\n"
            "  Or run:  pip install ultralytics  then  yolo export model=yolov8n.pt\n"
            "\n"
            "WD14 Tagger  (automatic — no manual download needed)\n"
            "  The tagger downloads SmilingWolf/wd-v1-4-vit-tagger-v2 from HuggingFace\n"
            "  on first use and caches it locally. Requires an internet connection\n"
            "  the first time only.",
            "── Vision / Captioning (at least one required for Generate caption) ──\n"
            "\n"
            "JoyCaption  (recommended — fast, LoRA-tuned)\n"
            "  Path : models/joycaption/\n"
            "  HuggingFace repo : fancyfeast/llama-joycaption-alpha-two-hf-llava\n"
            "  Download command :\n"
            "    huggingface-cli download fancyfeast/llama-joycaption-alpha-two-hf-llava \\\n"
            "        --local-dir models/joycaption\n"
            "\n"
            "Florence2  (lighter, good for objects / scenes)\n"
            "  Path : models/florence2/\n"
            "  HuggingFace repo : microsoft/Florence-2-large\n"
            "  Download command :\n"
            "    huggingface-cli download microsoft/Florence-2-large \\\n"
            "        --local-dir models/florence2\n"
            "\n"
            "Gemma3  (Google — requires a HuggingFace account and licence acceptance)\n"
            "  Path : models/gemma3/\n"
            "  HuggingFace repo : google/gemma-3-4b-it\n"
            "  Accept licence at https://huggingface.co/google/gemma-3-4b-it, then:\n"
            "    huggingface-cli login\n"
            "    huggingface-cli download google/gemma-3-4b-it \\\n"
            "        --local-dir models/gemma3",
            "── Caption Finalization LLM (optional — improves caption quality) ──\n"
            "\n"
            "Wizard-Vicuna 7B Uncensored GGUF\n"
            "  This GGUF model takes the raw tags and VLM description and rewrites\n"
            "  them into polished natural-language captions. It is optional — the\n"
            "  app will use the raw VLM output if it is not present.\n"
            "\n"
            "  Path : models/Wizard_Vicuna/Wizard-Vicuna-7B-Uncensored.Q4_K_M.gguf\n"
            "  HuggingFace repo : TheBloke/Wizard-Vicuna-7B-Uncensored-GGUF\n"
            "  Download command :\n"
            "    huggingface-cli download TheBloke/Wizard-Vicuna-7B-Uncensored-GGUF \\\n"
            "        Wizard-Vicuna-7B-Uncensored.Q4_K_M.gguf \\\n"
            "        --local-dir models/Wizard_Vicuna\n"
            "  Requires:  pip install llama-cpp-python  (with CUDA support for GPU offload)",
            "── Installing the huggingface-cli ──\n"
            "\n"
            "  pip install huggingface_hub\n"
            "\n"
            "For large models (JoyCaption, Gemma3) a GPU with at least 8 GB VRAM is\n"
            "recommended. Florence2 and Wizard-Vicuna can run on 4–6 GB VRAM.\n"
            "The app manages loading and unloading models automatically to fit within\n"
            "available VRAM as you move between wizard steps.",
        ],
    ),
    (
        "Tips & Troubleshooting",
        [
            "Models and VRAM:\n"
            "  • The app manages GPU VRAM automatically, loading and unloading models "
            "as you move between steps.\n"
            "  • If you have limited VRAM (< 8 GB), process images in smaller batches "
            "and avoid running Batch caption while the tagger is loaded.",
            "Profiles:\n"
            "  • Use profiles (Profile dropdown → Manage…) to save different settings "
            "for different projects — each profile stores folder paths, trigger words, "
            "caption format, system prompt, and UI preferences.",
            "Settings:\n"
            "  • The Settings button (gear icon) opens per-profile options including "
            "UI scale, appearance theme, default trigger words, find/replace rules, "
            "and the LLM system prompt used during caption finalization.",
            "Caption System Prompt:\n"
            "  • The system prompt in Settings controls what the LLM is told about its "
            "task during the finalization caption pass. Customise it per profile for "
            "different styles (e.g. anime vs. realistic photography).",
        ],
    ),
]


def open_tutorial_dialog(parent):
    """Open the getting-started tutorial as a modal window."""
    d = ctk.CTkToplevel(parent)
    d.title("Getting Started — LoRA Dataset Manager")
    d.geometry("720x640")
    d.resizable(True, True)
    d.transient(parent)
    d.grab_set()
    d.focus_set()

    # Header
    header = ctk.CTkFrame(d, fg_color=("gray85", "gray20"), corner_radius=0)
    header.pack(fill="x", padx=0, pady=0)
    ctk.CTkLabel(
        header,
        text="Getting Started Guide",
        font=ctk.CTkFont(size=18, weight="bold"),
    ).pack(side="left", padx=20, pady=12)
    ctk.CTkLabel(
        header,
        text="How to build a LoRA training dataset",
        font=ctk.CTkFont(size=12),
        text_color=("gray40", "gray70"),
    ).pack(side="left", padx=(0, 20), pady=12)

    # Scrollable body
    scroll = ctk.CTkScrollableFrame(d)
    scroll.pack(fill="both", expand=True, padx=0, pady=0)
    scroll.grid_columnconfigure(0, weight=1)

    for section_idx, (title, paragraphs) in enumerate(_SECTIONS):
        # Section header bar
        sec_header = ctk.CTkFrame(scroll, fg_color=("gray80", "gray25"), corner_radius=6)
        sec_header.grid(row=section_idx * 2, column=0, sticky="ew", padx=12, pady=(14, 2))
        ctk.CTkLabel(
            sec_header,
            text=title,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).pack(anchor="w", padx=12, pady=6)

        # Body text
        body_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        body_frame.grid(row=section_idx * 2 + 1, column=0, sticky="ew", padx=24, pady=(0, 4))
        body_frame.grid_columnconfigure(0, weight=1)
        for para in paragraphs:
            ctk.CTkLabel(
                body_frame,
                text=para,
                anchor="nw",
                justify="left",
                wraplength=620,
                font=ctk.CTkFont(size=12),
            ).pack(anchor="w", pady=(4, 0))

    # Footer close button
    footer = ctk.CTkFrame(d, fg_color="transparent")
    footer.pack(fill="x", padx=20, pady=(8, 12))
    ctk.CTkButton(footer, text="Close", width=100, command=d.destroy).pack(side="right")
