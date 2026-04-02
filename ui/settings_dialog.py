"""Settings dialog: text size (UI scale), appearance, LLM/caption defaults. Saved to current profile."""

import customtkinter as ctk
from tkinter import messagebox

from core.data.profiles import get_profiles_manager
from core.config import CAPTION_SYSTEM_PROMPT
from ui.tooltip import add_tooltip


def open_settings_dialog(parent, on_applied_callback=None):
    """Open a modal settings window. on_applied_callback() is called after Save (so app can apply theme/scale)."""
    profiles = get_profiles_manager()
    profile = profiles.get_current_profile()
    d = ctk.CTkToplevel(parent)
    d.title("Settings")
    d.geometry("560x520")
    d.transient(parent)
    d.grab_set()
    main = ctk.CTkScrollableFrame(d)
    main.pack(fill="both", expand=True, padx=15, pady=15)
    main.grid_columnconfigure(1, weight=1)

    row = 0
    ctk.CTkLabel(main, text="Interface", font=ctk.CTkFont(weight="bold")).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 5))
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

    row += 1
    ctk.CTkLabel(main, text="Caption / LLM defaults", font=ctk.CTkFont(weight="bold")).grid(row=row, column=0, columnspan=2, sticky="w", pady=(15, 5))
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

    # Caption system prompt (per profile)
    ctk.CTkLabel(main, text="Caption system prompt (for this profile):", wraplength=420).grid(row=row, column=0, columnspan=2, sticky="nw", padx=(0, 10), pady=(8, 3))
    system_prompt_text = ctk.CTkTextbox(main, height=120, width=280, wrap="word")
    system_prompt_text.grid(row=row, column=1, sticky="w", pady=3)
    add_tooltip(system_prompt_text, "System prompt sent to the LLM during caption finalization for this profile")
    current_prompt = profile.get("caption_system_prompt") or CAPTION_SYSTEM_PROMPT
    system_prompt_text.insert("1.0", current_prompt)
    row += 1

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
