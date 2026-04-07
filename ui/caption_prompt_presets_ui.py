"""Shared UI helpers for caption system/user prompt presets (Step 3 and Settings)."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog
from typing import Callable, List, Optional, Tuple

import customtkinter as ctk

from core.data.caption_prompt_presets import (
    build_menu_values,
    is_saved_menu_label,
    resolve_selection,
    saved_name_from_menu_label,
)
from core.data.profiles import get_profiles_manager, ProfilesManager
from ui.tooltip import add_tooltip

MENU_PLACEHOLDER = "— Select preset —"


def preset_menu_values(pm: ProfilesManager) -> List[str]:
    return [MENU_PLACEHOLDER] + build_menu_values(pm.get_caption_prompt_library())


def configure_preset_option_menu(
    menu: ctk.CTkOptionMenu,
    var: tk.StringVar,
    pm: ProfilesManager,
) -> None:
    vals = preset_menu_values(pm)
    menu.configure(values=vals)
    if var.get() not in vals:
        var.set(MENU_PLACEHOLDER)


def apply_preset_selection(
    menu_value: str,
    *,
    set_system_text: Callable[[str], None],
    set_user_text: Callable[[str], None],
    save_system_to_profile: Callable[[], None],
    pm: ProfilesManager,
) -> bool:
    """Apply the chosen row to widgets and persist system prompt to profile. Returns False if invalid."""
    if not menu_value or menu_value == MENU_PLACEHOLDER:
        return False
    resolved = resolve_selection(menu_value, pm.get_caption_prompt_library())
    if resolved is None:
        return False
    system, user = resolved
    set_system_text(system)
    set_user_text(user)
    save_system_to_profile()
    return True


def save_current_as_preset(
    parent: tk.Misc,
    *,
    get_system: Callable[[], str],
    get_user: Callable[[], str],
    on_saved: Callable[[str], None],
    pm: Optional[ProfilesManager] = None,
) -> None:
    pm = pm or get_profiles_manager()
    top = parent.winfo_toplevel()
    name = simpledialog.askstring(
        "Save caption preset",
        "Name for this preset (system + user prompt):",
        parent=top,
    )
    if name is None:
        return
    name = name.strip()
    if not name:
        messagebox.showwarning("Save preset", "Name cannot be empty.", parent=top)
        return
    final = pm.add_caption_prompt_library_entry(name, get_system(), get_user())
    on_saved(final)


def delete_saved_preset(
    parent: tk.Misc,
    menu_value: str,
    *,
    on_deleted: Callable[[], None],
    pm: Optional[ProfilesManager] = None,
) -> None:
    pm = pm or get_profiles_manager()
    if not is_saved_menu_label(menu_value):
        return
    sname = saved_name_from_menu_label(menu_value)
    if not sname:
        return
    top = parent.winfo_toplevel()
    if not messagebox.askyesno(
        "Delete preset",
        f"Remove saved preset “{sname}”?",
        parent=top,
    ):
        return
    if pm.remove_caption_prompt_library_entry(sname):
        on_deleted()


def build_preset_row(
    parent: ctk.CTkFrame,
    *,
    set_system_text: Callable[[str], None],
    set_user_text: Callable[[str], None],
    save_system_to_profile: Callable[[], None],
    get_system_text: Callable[[], str],
    get_user_text: Callable[[], str],
) -> Tuple[Callable[[], None], tk.StringVar]:
    """Pack preset controls. Returns (refresh_menu, menu_var)."""
    pm = get_profiles_manager()
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", pady=(0, 6))

    ctk.CTkLabel(row, text="Caption presets:", font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 6))
    var = tk.StringVar(value=MENU_PLACEHOLDER)
    menu = ctk.CTkOptionMenu(row, variable=var, values=preset_menu_values(pm), width=200)
    menu.pack(side="left", padx=(0, 4))

    def refresh_menu() -> None:
        configure_preset_option_menu(menu, var, pm)

    def do_apply() -> None:
        ok = apply_preset_selection(
            var.get(),
            set_system_text=set_system_text,
            set_user_text=set_user_text,
            save_system_to_profile=save_system_to_profile,
            pm=pm,
        )
        if not ok:
            messagebox.showinfo(
                "Caption presets",
                "Choose a built-in or saved preset from the list, then click Apply.",
                parent=parent.winfo_toplevel(),
            )

    def do_save() -> None:
        save_current_as_preset(
            parent,
            get_system=get_system_text,
            get_user=get_user_text,
            on_saved=lambda _final: refresh_menu(),
            pm=pm,
        )

    def do_delete() -> None:
        delete_saved_preset(parent, var.get(), on_deleted=refresh_menu, pm=pm)
        var.set(MENU_PLACEHOLDER)

    btn_apply = ctk.CTkButton(row, text="Apply", width=64, command=do_apply)
    btn_apply.pack(side="left", padx=2)
    btn_save = ctk.CTkButton(row, text="Save current…", width=100, command=do_save)
    btn_save.pack(side="left", padx=2)
    btn_del = ctk.CTkButton(row, text="Delete saved", width=92, command=do_delete)
    btn_del.pack(side="left", padx=2)

    add_tooltip(
        menu,
        "Built-in: “General descriptive” suits everyday or SFW captions without forcing every tag literally; "
        "“LoRA / full tag fidelity” matches the app default for training data. "
        "Saved presets live in your config file. Apply loads them below and saves the system prompt to this profile.",
    )
    add_tooltip(btn_apply, "Load the selected preset into the system and user prompt fields.")
    add_tooltip(btn_save, "Save the current system and user prompts as a named preset in your library.")
    add_tooltip(btn_del, "Remove the selected saved preset (built-ins cannot be deleted).")

    return refresh_menu, var
