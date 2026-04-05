"""Settings dialog: text size (UI scale), appearance, LLM/caption defaults. Saved to current profile."""

import customtkinter as ctk
from tkinter import messagebox
import threading

from core.data.profiles import get_profiles_manager
from core.config import CAPTION_SYSTEM_PROMPT
from ui.tooltip import add_tooltip

_SOURCE_LABELS = ["local", "ollama", "openai", "anthropic", "gemini"]
_LOCAL_MODELS = ["joycaption", "florence2", "gemma3"]
_OPENAI_MODELS = ["gpt-4o", "gpt-4-turbo", "gpt-4o-mini"]
_ANTHROPIC_MODELS = [
    "claude-3-5-haiku-20241022", "claude-3-5-sonnet-20241022",
    "claude-3-opus-20240229",
]
_GEMINI_MODELS = ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]


def open_settings_dialog(parent, on_applied_callback=None):
    """Open a modal settings window. on_applied_callback() is called after Save (so app can apply theme/scale)."""
    profiles = get_profiles_manager()
    profile = profiles.get_current_profile()
    backend_cfg = profiles.get_caption_backend_settings()

    d = ctk.CTkToplevel(parent)
    d.title("Settings")
    d.geometry("600x780")
    d.transient(parent)
    d.grab_set()
    main = ctk.CTkScrollableFrame(d)
    main.pack(fill="both", expand=True, padx=15, pady=15)
    main.grid_columnconfigure(1, weight=1)

    row = 0
    ctk.CTkLabel(main, text="Interface", font=ctk.CTkFont(weight="bold")).grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 5))
    row += 1
    ctk.CTkLabel(main, text="UI scale:").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
    scale_var = ctk.DoubleVar(value=float(profile.get("ui_scaling", 1.0)))
    scale_slider = ctk.CTkSlider(main, from_=0.9, to=1.4, variable=scale_var, width=160, command=lambda v: scale_label.configure(text=f"{float(v):.2f}"))
    scale_slider.grid(row=row, column=1, sticky="w", pady=3)
    add_tooltip(scale_slider, "Zoom all UI elements; requires restart to fully apply")
    scale_label = ctk.CTkLabel(main, text=f"{scale_var.get():.2f}")
    scale_label.grid(row=row, column=2, sticky="w", padx=(8, 0), pady=3)
    row += 1
    ctk.CTkLabel(main, text="(0.9 = smaller, 1.4 = larger). Applied at startup.", wraplength=420).grid(row=row, column=1, columnspan=2, sticky="w", pady=(0, 5))
    row += 1
    ctk.CTkLabel(main, text="Text size:").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
    text_scale_var = ctk.DoubleVar(value=float(profile.get("text_scale", 1.0)))
    def _text_scale_fmt(v):
        pct = int(float(v) * 100)
        return f"{pct}%"
    text_scale_slider = ctk.CTkSlider(main, from_=0.9, to=1.5, variable=text_scale_var, width=160,
                                      command=lambda v: text_scale_label.configure(text=_text_scale_fmt(v)))
    text_scale_slider.grid(row=row, column=1, sticky="w", pady=3)
    add_tooltip(text_scale_slider, "Scale text labels independently of UI zoom (90%–150%)")
    text_scale_label = ctk.CTkLabel(main, text=_text_scale_fmt(text_scale_var.get()))
    text_scale_label.grid(row=row, column=2, sticky="w", padx=(8, 0), pady=3)
    row += 1
    ctk.CTkLabel(main, text="(90%–150%. Affects labels and text for accessibility.)", wraplength=420).grid(row=row, column=1, columnspan=2, sticky="w", pady=(0, 8))
    row += 1
    ctk.CTkLabel(main, text="Appearance:").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
    appearance_var = ctk.StringVar(value=profile.get("appearance_mode", "dark"))
    appearance_menu = ctk.CTkOptionMenu(main, variable=appearance_var, values=["dark", "light", "system"], width=120)
    appearance_menu.grid(row=row, column=1, sticky="w", pady=3)
    add_tooltip(appearance_menu, "Switch between dark, light, or system color theme")
    row += 1

    # ── Smart Detection ────────────────────────────────────────────────────
    row += 1
    ctk.CTkLabel(main, text="Smart Detection", font=ctk.CTkFont(weight="bold")).grid(row=row, column=0, columnspan=3, sticky="w", pady=(15, 5))
    row += 1
    nudenet_var = ctk.BooleanVar(value=bool(profile.get("enable_nudenet", False)))
    nudenet_cb = ctk.CTkCheckBox(main, text="Enable NudeNet body-part detection", variable=nudenet_var)
    nudenet_cb.grid(row=row, column=0, columnspan=3, sticky="w", pady=3)
    add_tooltip(nudenet_cb,
                "Show body-part detection controls on the Crop & Sort tab.\n"
                "Requires the 'nudenet' package to be installed.\n"
                "Off by default — toggle on and save to enable per-profile.")
    row += 1
    ctk.CTkLabel(main,
                 text="Install: pip install nudenet    (off by default)",
                 wraplength=420, text_color="gray60").grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 8))
    row += 1

    # ── Caption / LLM defaults ──────────────────────────────────────────────
    row += 1
    ctk.CTkLabel(main, text="Caption / LLM defaults", font=ctk.CTkFont(weight="bold")).grid(row=row, column=0, columnspan=3, sticky="w", pady=(15, 5))
    row += 1
    ctk.CTkLabel(main, text="Default trigger words:").grid(row=row, column=0, sticky="nw", padx=(0, 10), pady=3)
    trigger_entry = ctk.CTkEntry(main, width=220, placeholder_text="e.g. mylora")
    trigger_entry.insert(0, profile.get("default_trigger_words", "") or "")
    trigger_entry.grid(row=row, column=1, sticky="w", pady=3)
    add_tooltip(trigger_entry, "Trigger words added to captions when creating a new session")
    row += 1
    ctk.CTkLabel(main, text="Default caption output:").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
    output_format_var = ctk.StringVar(value=profile.get("default_output_format", "Natural language"))
    _out_fmt_menu = ctk.CTkOptionMenu(main, variable=output_format_var, values=["Tags only", "Natural language", "Both"], width=160)
    _out_fmt_menu.grid(row=row, column=1, sticky="w", pady=3)
    add_tooltip(_out_fmt_menu, "Which output format to default to on Step 3 (Tags only, Natural language, or Both)")
    row += 1
    ctk.CTkLabel(main, text="Find/replace (one per line: find|replace):", wraplength=420).grid(row=row, column=0, columnspan=2, sticky="nw", padx=(0, 10), pady=(8, 3))
    fr_text = ctk.CTkTextbox(main, height=80, width=280)
    fr_text.grid(row=row, column=1, sticky="w", pady=3)
    add_tooltip(fr_text, "One substitution per line in the format: find|replace")
    default_fr = profile.get("default_find_replace") or []
    if isinstance(default_fr, list):
        fr_text.insert("1.0", "\n".join(f"{a}|{b}" for a, b in default_fr))
    row += 1

    ctk.CTkLabel(main, text="Caption system prompt:", wraplength=420).grid(row=row, column=0, columnspan=2, sticky="nw", padx=(0, 10), pady=(8, 3))
    system_prompt_text = ctk.CTkTextbox(main, height=100, width=280, wrap="word")
    system_prompt_text.grid(row=row, column=1, sticky="w", pady=3)
    add_tooltip(system_prompt_text, "System prompt sent to the LLM during caption finalization for this profile")
    current_prompt = profile.get("caption_system_prompt") or CAPTION_SYSTEM_PROMPT
    system_prompt_text.insert("1.0", current_prompt)
    row += 1

    # ── Caption Model / Backend ─────────────────────────────────────────────
    row += 1
    ctk.CTkLabel(main, text="Caption Model / Backend", font=ctk.CTkFont(weight="bold")).grid(row=row, column=0, columnspan=3, sticky="w", pady=(15, 5))
    row += 1
    ctk.CTkLabel(main, text="Caption source:").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
    source_var = ctk.StringVar(value=backend_cfg.get("caption_source", "local"))
    source_menu = ctk.CTkOptionMenu(main, variable=source_var, values=_SOURCE_LABELS, width=140)
    source_menu.grid(row=row, column=1, sticky="w", pady=3)
    add_tooltip(source_menu, "Where to send captioning requests: local models, Ollama server, or remote API")
    row += 1

    # Rows that show/hide depending on source selection
    # -- local model row --
    local_label = ctk.CTkLabel(main, text="Local model:")
    local_var = ctk.StringVar(value=backend_cfg.get("caption_local_model", "joycaption"))
    local_menu = ctk.CTkOptionMenu(main, variable=local_var, values=_LOCAL_MODELS, width=140)
    add_tooltip(local_menu, "Which local HuggingFace model to use for captioning (joycaption, florence2, gemma3)")

    # -- Ollama rows --
    ollama_url_label = ctk.CTkLabel(main, text="Ollama server URL:")
    ollama_url_entry = ctk.CTkEntry(main, width=220, placeholder_text="http://localhost:11434")
    ollama_url_entry.insert(0, backend_cfg.get("ollama_url", "http://localhost:11434"))
    add_tooltip(ollama_url_entry, "Base URL of your running Ollama server")
    ollama_model_label = ctk.CTkLabel(main, text="Ollama model:")
    ollama_model_var = ctk.StringVar(value=backend_cfg.get("ollama_model", "llava"))
    ollama_model_entry = ctk.CTkEntry(main, width=160, textvariable=ollama_model_var, placeholder_text="llava")
    add_tooltip(ollama_model_entry, "Ollama model tag (e.g. llava, bakllava, moondream2)")
    ollama_fetch_btn = ctk.CTkButton(main, text="Fetch models", width=110)
    add_tooltip(ollama_fetch_btn, "Fetch available models from the Ollama server and fill the model field")

    # -- OpenAI rows --
    oai_key_label = ctk.CTkLabel(main, text="OpenAI API key:")
    oai_key_entry = ctk.CTkEntry(main, width=260, show="*", placeholder_text="sk-…")
    oai_key_entry.insert(0, backend_cfg.get("openai_api_key", ""))
    add_tooltip(oai_key_entry, "Your OpenAI API key — get one at https://platform.openai.com/api-keys")
    oai_model_label = ctk.CTkLabel(main, text="OpenAI model:")
    oai_model_var = ctk.StringVar(value=backend_cfg.get("openai_model", "gpt-4o"))
    oai_model_menu = ctk.CTkOptionMenu(main, variable=oai_model_var, values=_OPENAI_MODELS, width=160)
    add_tooltip(oai_model_menu, "Vision-capable OpenAI model to use")

    # -- Anthropic rows --
    ant_key_label = ctk.CTkLabel(main, text="Anthropic API key:")
    ant_key_entry = ctk.CTkEntry(main, width=260, show="*", placeholder_text="sk-ant-…")
    ant_key_entry.insert(0, backend_cfg.get("anthropic_api_key", ""))
    add_tooltip(ant_key_entry, "Your Anthropic API key — get one at https://console.anthropic.com")
    ant_model_label = ctk.CTkLabel(main, text="Anthropic model:")
    ant_model_var = ctk.StringVar(value=backend_cfg.get("anthropic_model", "claude-3-5-haiku-20241022"))
    ant_model_menu = ctk.CTkOptionMenu(main, variable=ant_model_var, values=_ANTHROPIC_MODELS, width=220)
    add_tooltip(ant_model_menu, "Claude model to use (haiku is cheapest, sonnet is best quality)")

    # -- Gemini rows --
    gem_key_label = ctk.CTkLabel(main, text="Gemini API key:")
    gem_key_entry = ctk.CTkEntry(main, width=260, show="*", placeholder_text="AIza…")
    gem_key_entry.insert(0, backend_cfg.get("gemini_api_key", ""))
    add_tooltip(gem_key_entry, "Your Google Gemini API key — get one at https://aistudio.google.com/app/apikey")
    gem_model_label = ctk.CTkLabel(main, text="Gemini model:")
    gem_model_var = ctk.StringVar(value=backend_cfg.get("gemini_model", "gemini-2.0-flash"))
    gem_model_menu = ctk.CTkOptionMenu(main, variable=gem_model_var, values=_GEMINI_MODELS, width=180)
    add_tooltip(gem_model_menu, "Google Gemini model to use")

    # Test connection button (bottom of backend section)
    test_btn_row = row + 20  # placeholder; we track actual row via _dynamic_rows
    test_status_label = ctk.CTkLabel(main, text="", text_color="gray70")

    # Track which rows are currently visible so we can show/hide cleanly
    _col0_pad = (0, 10)
    _all_backend_widgets = [
        (local_label, local_menu, None),
        (ollama_url_label, ollama_url_entry, None),
        (ollama_model_label, ollama_model_entry, ollama_fetch_btn),
        (oai_key_label, oai_key_entry, None),
        (oai_model_label, oai_model_menu, None),
        (ant_key_label, ant_key_entry, None),
        (ant_model_label, ant_model_menu, None),
        (gem_key_label, gem_key_entry, None),
        (gem_model_label, gem_model_menu, None),
    ]
    _source_widgets = {
        "local": [0],
        "ollama": [1, 2],
        "openai": [3, 4],
        "anthropic": [5, 6],
        "gemini": [7, 8],
    }

    # Assign each widget group a fixed grid row so show/hide is stable
    _base_row = row  # current row before dynamic section
    for idx, (lbl, wid, extra) in enumerate(_all_backend_widgets):
        r = _base_row + idx
        lbl.grid(row=r, column=0, sticky="w", padx=_col0_pad, pady=3)
        wid.grid(row=r, column=1, sticky="w", pady=3)
        if extra:
            extra.grid(row=r, column=2, sticky="w", padx=(6, 0), pady=3)

    row = _base_row + len(_all_backend_widgets)
    test_conn_btn = ctk.CTkButton(main, text="Test connection", width=130)
    test_conn_btn.grid(row=row, column=1, sticky="w", pady=(6, 2))
    add_tooltip(test_conn_btn, "Send a test caption request using the current backend settings")
    row += 1
    test_status_label.grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 8))
    row += 1

    def _refresh_backend_rows(*_):
        src = source_var.get()
        visible = set(_source_widgets.get(src, []))
        for idx, (lbl, wid, extra) in enumerate(_all_backend_widgets):
            if idx in visible:
                lbl.grid()
                wid.grid()
                if extra:
                    extra.grid()
            else:
                lbl.grid_remove()
                wid.grid_remove()
                if extra:
                    extra.grid_remove()

    source_var.trace_add("write", _refresh_backend_rows)
    _refresh_backend_rows()  # apply immediately

    def _fetch_ollama_models():
        url = ollama_url_entry.get().strip() or "http://localhost:11434"
        test_status_label.configure(text="Fetching Ollama models…", text_color="gray70")
        def _do():
            try:
                from core.ai.caption_backends import OllamaBackend
                models = OllamaBackend.list_models(base_url=url)
                if models:
                    ollama_model_var.set(models[0])
                    test_status_label.configure(
                        text=f"Found {len(models)} model(s): {', '.join(models[:5])}",
                        text_color="green",
                    )
                else:
                    test_status_label.configure(text="No models found or Ollama not running.", text_color="orange")
            except Exception as exc:
                test_status_label.configure(text=f"Error: {exc}", text_color="red")
        threading.Thread(target=_do, daemon=True).start()

    ollama_fetch_btn.configure(command=_fetch_ollama_models)

    def _test_connection():
        src = source_var.get()
        test_status_label.configure(text=f"Testing {src} connection…", text_color="gray70")
        fake_profile = {
            "caption_source": src,
            "caption_local_model": local_var.get(),
            "ollama_url": ollama_url_entry.get().strip(),
            "ollama_model": ollama_model_var.get(),
            "openai_api_key": oai_key_entry.get().strip(),
            "openai_model": oai_model_var.get(),
            "anthropic_api_key": ant_key_entry.get().strip(),
            "anthropic_model": ant_model_var.get(),
            "gemini_api_key": gem_key_entry.get().strip(),
            "gemini_model": gem_model_var.get(),
        }
        def _do():
            try:
                from core.ai.caption_backends import get_caption_backend
                from pathlib import Path
                import tempfile, os
                from PIL import Image as PILImage
                backend = get_caption_backend(fake_profile)
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                img = PILImage.new("RGB", (64, 64), color=(128, 128, 128))
                img.save(tmp_path, "JPEG")
                result = backend.generate(tmp_path, tags=["test"], prompt="Describe this image briefly.")
                os.unlink(tmp_path)
                if result:
                    test_status_label.configure(text=f"OK — response: {result[:80]}…", text_color="green")
                else:
                    test_status_label.configure(text="Connected but got empty response.", text_color="orange")
            except Exception as exc:
                test_status_label.configure(text=f"Failed: {exc}", text_color="red")
        threading.Thread(target=_do, daemon=True).start()

    test_conn_btn.configure(command=_test_connection)

    # ── Save / Cancel ───────────────────────────────────────────────────────
    def save():
        scale = scale_var.get()
        appearance = appearance_var.get()
        trigger = trigger_entry.get().strip()
        fr_lines = fr_text.get("1.0", "end-1c").strip().splitlines()
        fr_pairs = []
        for line in fr_lines:
            line = line.strip()
            if "|" in line:
                a, _, b = line.partition("|")
                fr_pairs.append([a.strip(), b.strip()])
        current = profiles.get_current_profile()
        name = profiles.config.get("current_profile", "User settings")
        text_scale = text_scale_var.get()
        current["ui_scaling"] = scale
        current["text_scale"] = text_scale
        current["appearance_mode"] = appearance
        current["default_trigger_words"] = trigger
        current["default_find_replace"] = fr_pairs
        current["default_output_format"] = output_format_var.get()
        current["caption_system_prompt"] = system_prompt_text.get("1.0", "end-1c").strip()
        current["enable_nudenet"] = nudenet_var.get()
        # Backend settings
        current["caption_source"] = source_var.get()
        current["caption_local_model"] = local_var.get()
        current["ollama_url"] = ollama_url_entry.get().strip()
        current["ollama_model"] = ollama_model_var.get()
        current["openai_api_key"] = oai_key_entry.get().strip()
        current["openai_model"] = oai_model_var.get()
        current["anthropic_api_key"] = ant_key_entry.get().strip()
        current["anthropic_model"] = ant_model_var.get()
        current["gemini_api_key"] = gem_key_entry.get().strip()
        current["gemini_model"] = gem_model_var.get()
        profiles.save_profile(name, current)
        ctk.set_appearance_mode(appearance)
        ctk.set_widget_scaling(scale)
        ctk.set_window_scaling(scale)
        if on_applied_callback:
            on_applied_callback()
        messagebox.showinfo("Settings", "Settings saved to current profile.", parent=d)
        d.destroy()

    btn_frame = ctk.CTkFrame(d, fg_color="transparent")
    btn_frame.pack(fill="x", padx=15, pady=(0, 15))
    _save_btn = ctk.CTkButton(btn_frame, text="Save", width=100, command=save)
    _save_btn.pack(side="right", padx=5)
    add_tooltip(_save_btn, "Save settings to the current profile")
    _cancel_btn = ctk.CTkButton(btn_frame, text="Cancel", width=100, fg_color="gray", command=d.destroy)
    _cancel_btn.pack(side="right")
    add_tooltip(_cancel_btn, "Discard changes and close")

    ctk.set_appearance_mode(appearance_var.get())
    ctk.set_widget_scaling(scale_var.get())
    ctk.set_window_scaling(scale_var.get())
