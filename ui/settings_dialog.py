"""Settings dialog — 3-tab layout: Interface / Caption / API & Models."""

import os
import sys
import subprocess
import threading
import customtkinter as ctk
from tkinter import messagebox

from core.data.profiles import get_profiles_manager
from core.config import CAPTION_SYSTEM_PROMPT
from ui.caption_prompt_presets_ui import build_preset_row
from ui.tooltip import add_tooltip

_SOURCE_LABELS = ["local", "ollama", "openai", "anthropic", "gemini"]
_LOCAL_MODELS = ["joycaption", "florence2", "gemma3"]
_OPENAI_MODELS = ["gpt-4o", "gpt-4-turbo", "gpt-4o-mini"]
_ANTHROPIC_MODELS = [
    "claude-3-5-haiku-20241022", "claude-3-5-sonnet-20241022",
    "claude-3-opus-20240229",
]
_GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
_COLOR_THEMES = ["blue", "green", "dark-blue"]


def open_settings_dialog(parent, on_applied_callback=None):
    """Open a modal settings window. on_applied_callback() is called after Save."""
    profiles = get_profiles_manager()
    profile = profiles.get_current_profile()
    backend_cfg = profiles.get_caption_backend_settings()

    d = ctk.CTkToplevel(parent)
    d.title("Settings")
    d.geometry("580x620")
    d.minsize(520, 520)
    d.transient(parent)
    d.grab_set()

    tabview = ctk.CTkTabview(d, anchor="nw")
    tabview.pack(fill="both", expand=True, padx=12, pady=(12, 0))

    tab_iface = tabview.add("Interface")
    tab_caption = tabview.add("Caption")
    tab_api = tabview.add("API & Models")

    # ─────────────────────────────────────────────────────────────
    # TAB 1 — Interface
    # ─────────────────────────────────────────────────────────────
    iface = ctk.CTkScrollableFrame(tab_iface, fg_color="transparent")
    iface.pack(fill="both", expand=True)
    iface.grid_columnconfigure(1, weight=1)

    row = 0

    # UI scale
    ctk.CTkLabel(iface, text="UI scale:").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
    scale_var = ctk.DoubleVar(value=float(profile.get("ui_scaling", 1.0)))
    scale_label = ctk.CTkLabel(iface, text=f"{scale_var.get():.2f}", width=42, anchor="e")
    scale_slider = ctk.CTkSlider(
        iface, from_=0.9, to=1.4, variable=scale_var, width=200,
        command=lambda v: scale_label.configure(text=f"{float(v):.2f}"),
    )
    scale_slider.grid(row=row, column=1, sticky="w", pady=3)
    scale_label.grid(row=row, column=2, sticky="w", padx=(8, 0), pady=3)
    add_tooltip(scale_slider, "Zoom all UI elements; requires restart to fully apply.\n0.9 = smaller, 1.4 = larger.")
    row += 1

    # Text size
    ctk.CTkLabel(iface, text="Text size:").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
    text_scale_var = ctk.DoubleVar(value=float(profile.get("text_scale", 1.0)))

    def _pct(v):
        return f"{int(float(v) * 100)}%"

    text_scale_label = ctk.CTkLabel(iface, text=_pct(text_scale_var.get()), width=42, anchor="e")
    text_scale_slider = ctk.CTkSlider(
        iface, from_=0.9, to=1.5, variable=text_scale_var, width=200,
        command=lambda v: text_scale_label.configure(text=_pct(v)),
    )
    text_scale_slider.grid(row=row, column=1, sticky="w", pady=3)
    text_scale_label.grid(row=row, column=2, sticky="w", padx=(8, 0), pady=3)
    add_tooltip(text_scale_slider, "Scale text labels independently of UI zoom (90%–150%).")
    row += 1

    # Appearance mode
    ctk.CTkLabel(iface, text="Appearance:").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
    appearance_var = ctk.StringVar(value=profile.get("appearance_mode", "dark"))
    appearance_menu = ctk.CTkOptionMenu(iface, variable=appearance_var, values=["dark", "light", "system"], width=130)
    appearance_menu.grid(row=row, column=1, sticky="w", pady=3)
    add_tooltip(appearance_menu, "Switch between dark, light, or system color theme.")
    row += 1

    # Color theme
    ctk.CTkLabel(iface, text="Color theme:").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
    color_theme_var = ctk.StringVar(value=profile.get("color_theme", "blue"))
    color_theme_menu = ctk.CTkOptionMenu(iface, variable=color_theme_var, values=_COLOR_THEMES, width=130)
    color_theme_menu.grid(row=row, column=1, sticky="w", pady=3)
    add_tooltip(
        color_theme_menu,
        "CTk accent color theme.\n"
        "blue = default blue highlights.\n"
        "green = green highlights.\n"
        "dark-blue = deeper navy highlights.\n"
        "Takes effect after Save + restart.",
    )
    row += 1

    # Hint row
    ctk.CTkLabel(
        iface,
        text="UI scale and color theme are applied at next startup.",
        text_color="gray60",
        wraplength=380,
    ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(2, 10))
    row += 1

    # ─────────────────────────────────────────────────────────────
    # TAB 2 — Caption
    # ─────────────────────────────────────────────────────────────
    cap = ctk.CTkScrollableFrame(tab_caption, fg_color="transparent")
    cap.pack(fill="both", expand=True)
    cap.grid_columnconfigure(1, weight=1)

    row = 0

    # Trigger words
    ctk.CTkLabel(cap, text="Default trigger words:").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
    trigger_entry = ctk.CTkEntry(cap, width=240, placeholder_text="e.g. mylora")
    trigger_entry.insert(0, profile.get("default_trigger_words", "") or "")
    trigger_entry.grid(row=row, column=1, sticky="w", pady=3)
    add_tooltip(trigger_entry, "Trigger words added to captions when creating a new session.")
    row += 1

    # Output format
    ctk.CTkLabel(cap, text="Default caption output:").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
    output_format_var = ctk.StringVar(value=profile.get("default_output_format", "Natural language"))
    out_fmt_menu = ctk.CTkOptionMenu(cap, variable=output_format_var, values=["Tags only", "Natural language", "Both"], width=160)
    out_fmt_menu.grid(row=row, column=1, sticky="w", pady=3)
    add_tooltip(out_fmt_menu, "Which output format to default to on Step 3 (Tags only, Natural language, or Both).")
    row += 1

    # Find / replace
    ctk.CTkLabel(cap, text="Find/replace\n(find|replace, one per line):", wraplength=160, justify="left").grid(
        row=row, column=0, sticky="nw", padx=(0, 10), pady=(8, 3))
    fr_text = ctk.CTkTextbox(cap, height=80, width=280)
    fr_text.grid(row=row, column=1, sticky="ew", pady=(8, 3))
    add_tooltip(fr_text, "One substitution per line in the format: find|replace")
    default_fr = profile.get("default_find_replace") or []
    if isinstance(default_fr, list):
        fr_text.insert("1.0", "\n".join(f"{a}|{b}" for a, b in default_fr))
    row += 1

    system_prompt_text = ctk.CTkTextbox(cap, height=110, width=280, wrap="word")
    current_prompt = profile.get("caption_system_prompt") or CAPTION_SYSTEM_PROMPT
    system_prompt_text.insert("1.0", current_prompt)

    user_preset_entry = ctk.CTkEntry(
        cap, width=280, placeholder_text="e.g. Focus on composition (optional)"
    )

    preset_host = ctk.CTkFrame(cap, fg_color="transparent")

    def _settings_save_system_to_profile() -> None:
        profiles.set_caption_system_prompt(system_prompt_text.get("1.0", "end-1c").strip())

    def _settings_set_system(s: str) -> None:
        system_prompt_text.delete("1.0", "end")
        system_prompt_text.insert("1.0", s)

    def _settings_set_user(s: str) -> None:
        user_preset_entry.delete(0, "end")
        if s:
            user_preset_entry.insert(0, s)

    build_preset_row(
        preset_host,
        set_system_text=_settings_set_system,
        set_user_text=_settings_set_user,
        save_system_to_profile=_settings_save_system_to_profile,
        get_system_text=lambda: system_prompt_text.get("1.0", "end-1c"),
        get_user_text=lambda: user_preset_entry.get(),
    )
    preset_host.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(8, 4))
    row += 1

    ctk.CTkLabel(cap, text="Optional user prompt:", wraplength=160, justify="left").grid(
        row=row, column=0, sticky="w", padx=(0, 10), pady=(3, 3))
    user_preset_entry.grid(row=row, column=1, sticky="ew", pady=(3, 3))
    add_tooltip(
        user_preset_entry,
        "Optional line saved with caption presets (Apply / Save current…). "
        "Step 3 has its own user prompt field for generation—copy over if you want the same text there.",
    )
    row += 1

    # System prompt
    ctk.CTkLabel(cap, text="Caption system prompt:", wraplength=160, justify="left").grid(
        row=row, column=0, sticky="nw", padx=(0, 10), pady=(8, 3))
    system_prompt_text.grid(row=row, column=1, sticky="ew", pady=(8, 3))
    add_tooltip(
        system_prompt_text,
        "System prompt sent to the LLM during caption generation for this profile. "
        "Caption presets (above) can load built-in or saved styles; built-in “General descriptive” is suited to non-training use.",
    )
    row += 1

    # ── Smart Detection ───────────────────────────────────────────
    sep = ctk.CTkFrame(cap, height=1, fg_color="gray40")
    sep.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(12, 6))
    row += 1

    ctk.CTkLabel(cap, text="Smart Detection", font=ctk.CTkFont(weight="bold")).grid(
        row=row, column=0, columnspan=3, sticky="w", pady=(0, 4))
    row += 1

    nudenet_var = ctk.BooleanVar(value=bool(profile.get("enable_nudenet", False)))
    nudenet_cb = ctk.CTkCheckBox(cap, text="Enable NudeNet body-part detection", variable=nudenet_var)
    nudenet_cb.grid(row=row, column=0, columnspan=3, sticky="w", pady=3)
    add_tooltip(
        nudenet_cb,
        "Show body-part detection controls on the Crop & Sort tab.\n"
        "Requires the 'nudenet' package: pip install nudenet\n"
        "Off by default — toggle on and save to enable per-profile.",
    )
    row += 1

    ctk.CTkLabel(cap, text="Install: pip install nudenet    (off by default)",
                 text_color="gray60", wraplength=380).grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 8))
    row += 1

    # ─────────────────────────────────────────────────────────────
    # TAB 3 — API & Models
    # ─────────────────────────────────────────────────────────────
    api = ctk.CTkScrollableFrame(tab_api, fg_color="transparent")
    api.pack(fill="both", expand=True)
    api.grid_columnconfigure(1, weight=1)

    row = 0

    ctk.CTkLabel(api, text="Caption source:").grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
    source_var = ctk.StringVar(value=backend_cfg.get("caption_source", "local"))
    source_menu = ctk.CTkOptionMenu(api, variable=source_var, values=_SOURCE_LABELS, width=140)
    source_menu.grid(row=row, column=1, sticky="w", pady=3)
    add_tooltip(source_menu, "Where to send captioning requests: local models, Ollama server, or remote API.")
    row += 1

    # ── dynamic backend rows ──────────────────────────────────────
    # local
    local_label = ctk.CTkLabel(api, text="Local model:")
    local_var = ctk.StringVar(value=backend_cfg.get("caption_local_model", "joycaption"))
    local_menu = ctk.CTkOptionMenu(api, variable=local_var, values=_LOCAL_MODELS, width=140)
    add_tooltip(local_menu, "Which local HuggingFace model to use for captioning.")

    # ollama
    ollama_url_label = ctk.CTkLabel(api, text="Ollama server URL:")
    ollama_url_entry = ctk.CTkEntry(api, width=240, placeholder_text="http://localhost:11434")
    ollama_url_entry.insert(0, backend_cfg.get("ollama_url", "http://localhost:11434"))
    add_tooltip(ollama_url_entry, "Base URL of your running Ollama server.")

    ollama_model_label = ctk.CTkLabel(api, text="Ollama model:")
    ollama_model_var = ctk.StringVar(value=backend_cfg.get("ollama_model", "llava"))
    ollama_model_entry = ctk.CTkEntry(api, width=160, textvariable=ollama_model_var, placeholder_text="llava")
    add_tooltip(ollama_model_entry, "Ollama model tag — type manually or use Fetch models to pick from the server.")
    ollama_fetch_btn = ctk.CTkButton(api, text="Fetch models", width=110)
    add_tooltip(ollama_fetch_btn, "Fetch available models from the Ollama server.")
    # Populated dropdown — hidden until a successful fetch
    ollama_model_picker_label = ctk.CTkLabel(api, text="Select model:")
    ollama_model_picker = ctk.CTkOptionMenu(api, variable=ollama_model_var, values=[""], width=200)
    add_tooltip(ollama_model_picker,
                "Click to select a model returned by Fetch models. "
                "The selection also updates the text entry above.")

    # openai
    oai_key_label = ctk.CTkLabel(api, text="OpenAI API key:")
    oai_key_entry = ctk.CTkEntry(api, width=260, show="*", placeholder_text="sk-…")
    oai_key_entry.insert(0, backend_cfg.get("openai_api_key", ""))
    add_tooltip(oai_key_entry, "Your OpenAI API key — get one at https://platform.openai.com/api-keys")

    oai_model_label = ctk.CTkLabel(api, text="OpenAI model:")
    oai_model_var = ctk.StringVar(value=backend_cfg.get("openai_model", "gpt-4o"))
    oai_model_menu = ctk.CTkOptionMenu(api, variable=oai_model_var, values=_OPENAI_MODELS, width=160)
    add_tooltip(oai_model_menu, "Vision-capable OpenAI model to use.")

    # anthropic
    ant_key_label = ctk.CTkLabel(api, text="Anthropic API key:")
    ant_key_entry = ctk.CTkEntry(api, width=260, show="*", placeholder_text="sk-ant-…")
    ant_key_entry.insert(0, backend_cfg.get("anthropic_api_key", ""))
    add_tooltip(ant_key_entry, "Your Anthropic API key — get one at https://console.anthropic.com")

    ant_model_label = ctk.CTkLabel(api, text="Anthropic model:")
    ant_model_var = ctk.StringVar(value=backend_cfg.get("anthropic_model", "claude-3-5-haiku-20241022"))
    ant_model_menu = ctk.CTkOptionMenu(api, variable=ant_model_var, values=_ANTHROPIC_MODELS, width=220)
    add_tooltip(ant_model_menu, "Claude model to use (haiku = fastest/cheapest, sonnet = best quality).")

    # gemini
    gem_key_label = ctk.CTkLabel(api, text="Gemini API key:")
    gem_key_entry = ctk.CTkEntry(api, width=260, show="*", placeholder_text="AIza…")
    gem_key_entry.insert(0, backend_cfg.get("gemini_api_key", ""))
    add_tooltip(gem_key_entry, "Your Google Gemini API key — get one at https://aistudio.google.com/app/apikey")

    gem_model_label = ctk.CTkLabel(api, text="Gemini model:")
    gem_model_var = ctk.StringVar(value=backend_cfg.get("gemini_model", "gemini-2.5-flash"))
    gem_model_menu = ctk.CTkOptionMenu(api, variable=gem_model_var, values=_GEMINI_MODELS, width=180)
    add_tooltip(gem_model_menu, "Google Gemini model to use (install: pip install google-genai).")

    _all_backend_widgets = [
        (local_label,              local_menu,             None),
        (ollama_url_label,         ollama_url_entry,       None),
        (ollama_model_label,       ollama_model_entry,     ollama_fetch_btn),
        (ollama_model_picker_label, ollama_model_picker,   None),
        (oai_key_label,            oai_key_entry,          None),
        (oai_model_label,          oai_model_menu,         None),
        (ant_key_label,            ant_key_entry,          None),
        (ant_model_label,          ant_model_menu,         None),
        (gem_key_label,            gem_key_entry,          None),
        (gem_model_label,          gem_model_menu,         None),
    ]
    _source_widgets = {
        "local":     [0],
        "ollama":    [1, 2],          # picker row (3) shown only after a successful fetch
        "openai":    [4, 5],
        "anthropic": [6, 7],
        "gemini":    [8, 9],
    }
    # Index of the picker row — hidden by default, revealed after a successful fetch
    _OLLAMA_PICKER_ROW = 3

    # Assign fixed grid rows inside tab_api
    _base_row = row
    for idx, (lbl, wid, extra) in enumerate(_all_backend_widgets):
        r = _base_row + idx
        lbl.grid(row=r, column=0, sticky="w", padx=(0, 10), pady=3)
        wid.grid(row=r, column=1, sticky="w", pady=3)
        if extra:
            extra.grid(row=r, column=2, sticky="w", padx=(6, 0), pady=3)

    row = _base_row + len(_all_backend_widgets)

    # Separator before test connection
    sep2 = ctk.CTkFrame(api, height=1, fg_color="gray40")
    sep2.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(10, 6))
    row += 1

    test_conn_btn = ctk.CTkButton(api, text="Test connection", width=130)
    test_conn_btn.grid(row=row, column=1, sticky="w", pady=(2, 2))
    add_tooltip(test_conn_btn, "Send a test caption request using the current backend settings.")
    row += 1

    test_status_label = ctk.CTkLabel(api, text="", text_color="gray70", wraplength=340)
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
    _refresh_backend_rows()

    def _fetch_ollama_models():
        url = ollama_url_entry.get().strip() or "http://localhost:11434"
        test_status_label.configure(text="Fetching Ollama models…", text_color="gray70")
        def _do():
            try:
                from core.ai.caption_backends import OllamaBackend
                models = OllamaBackend.list_models(base_url=url)
                if models:
                    ollama_model_picker.configure(values=models)
                    # Keep current value if it's in the list; otherwise default to first
                    cur = ollama_model_var.get()
                    ollama_model_var.set(cur if cur in models else models[0])
                    # Show the picker row
                    lbl, wid, _ = _all_backend_widgets[_OLLAMA_PICKER_ROW]
                    lbl.grid()
                    wid.grid()
                    test_status_label.configure(
                        text=f"Found {len(models)} model(s) — select one below.",
                        text_color="green",
                    )
                else:
                    test_status_label.configure(
                        text="No models found or Ollama not running.", text_color="orange"
                    )
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

    # ─────────────────────────────────────────────────────────────
    # Save / Cancel  (outside the tabview, always visible)
    # ─────────────────────────────────────────────────────────────

    # Snapshot the original restart-sensitive values so we can detect changes
    _orig_scale = float(profile.get("ui_scaling", 1.0))
    _orig_theme = profile.get("color_theme", "blue")

    def _do_restart():
        """Spawn a fresh process and terminate the current one."""
        try:
            parent.winfo_toplevel().destroy()
        except Exception:
            pass
        subprocess.Popen([sys.executable] + sys.argv)
        sys.exit(0)

    def save():
        fr_lines = fr_text.get("1.0", "end-1c").strip().splitlines()
        fr_pairs = []
        for line in fr_lines:
            line = line.strip()
            if "|" in line:
                a, _, b = line.partition("|")
                fr_pairs.append([a.strip(), b.strip()])

        current = profiles.get_current_profile()
        name = profiles.config.get("current_profile", "User settings")

        new_scale = scale_var.get()
        new_theme = color_theme_var.get()

        # Interface
        current["ui_scaling"] = new_scale
        current["text_scale"] = text_scale_var.get()
        current["appearance_mode"] = appearance_var.get()
        current["color_theme"] = new_theme

        # Caption
        current["default_trigger_words"] = trigger_entry.get().strip()
        current["default_find_replace"] = fr_pairs
        current["default_output_format"] = output_format_var.get()
        current["caption_system_prompt"] = system_prompt_text.get("1.0", "end-1c").strip()
        current["enable_nudenet"] = nudenet_var.get()

        # API & Models
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

        ctk.set_appearance_mode(appearance_var.get())
        ctk.set_widget_scaling(new_scale)
        ctk.set_window_scaling(new_scale)

        if on_applied_callback:
            on_applied_callback()

        # Check whether a restart is needed (scale or theme changed)
        needs_restart = (
            abs(new_scale - _orig_scale) > 0.001
            or new_theme != _orig_theme
        )

        if needs_restart:
            _show_restart_dialog()
        else:
            messagebox.showinfo("Settings", "Settings saved.", parent=d)
            d.destroy()

    def _show_restart_dialog():
        """Modal dialog offering an immediate restart when required settings changed."""
        rd = ctk.CTkToplevel(d)
        rd.title("Restart required")
        rd.geometry("380x160")
        rd.resizable(False, False)
        rd.transient(d)
        rd.grab_set()

        ctk.CTkLabel(
            rd,
            text="Settings saved.\n\nUI scale and color theme changes take full\neffect after a restart.",
            wraplength=340,
            justify="center",
        ).pack(pady=(20, 12))

        btn_row = ctk.CTkFrame(rd, fg_color="transparent")
        btn_row.pack(pady=(0, 16))

        def _later():
            rd.destroy()
            d.destroy()

        ctk.CTkButton(btn_row, text="Restart Now", width=130, command=_do_restart).pack(side="left", padx=8)
        add_tooltip(
            btn_row.winfo_children()[0],
            "Close the app and immediately relaunch it to apply all changes.",
        )
        ctk.CTkButton(btn_row, text="Later", width=100, fg_color="gray", command=_later).pack(side="left", padx=8)
        add_tooltip(
            btn_row.winfo_children()[1],
            "Close settings — changes will apply on the next manual restart.",
        )

    btn_frame = ctk.CTkFrame(d, fg_color="transparent")
    btn_frame.pack(fill="x", padx=12, pady=(6, 12))

    _cancel_btn = ctk.CTkButton(btn_frame, text="Cancel", width=100, fg_color="gray", command=d.destroy)
    _cancel_btn.pack(side="right", padx=(4, 0))
    add_tooltip(_cancel_btn, "Discard changes and close.")

    _save_btn = ctk.CTkButton(btn_frame, text="Save", width=100, command=save)
    _save_btn.pack(side="right")
    add_tooltip(_save_btn, "Save all settings to the current profile.")

    # Apply live appearance immediately when the dropdown changes
    ctk.set_appearance_mode(appearance_var.get())
    ctk.set_widget_scaling(scale_var.get())
    ctk.set_window_scaling(scale_var.get())
