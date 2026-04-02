"""Profile Manager dialog: create, rename, delete, and select profiles."""

import customtkinter as ctk
from tkinter import messagebox, simpledialog

from core.data.profiles import get_profiles_manager
from ui.tooltip import add_tooltip


def open_profile_manager(parent, on_profiles_changed=None):
    """Open a modal dialog to manage profiles (New/Rename/Delete/Select)."""
    profiles = get_profiles_manager()

    d = ctk.CTkToplevel(parent)
    d.title("Manage Profiles")
    d.geometry("420x360")
    d.transient(parent)
    d.grab_set()

    main = ctk.CTkFrame(d)
    main.pack(fill="both", expand=True, padx=15, pady=15)
    main.grid_columnconfigure(0, weight=1)
    main.grid_rowconfigure(0, weight=1)

    listbox = ctk.CTkScrollableFrame(main)
    listbox.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0, 10))

    state = {"selected": profiles.config.get("current_profile", "User settings")}

    def refresh_list():
        for w in listbox.winfo_children():
            w.destroy()
        names = profiles.list_profiles()
        if not names:
            ctk.CTkLabel(listbox, text="No profiles defined.", text_color="gray60").pack(anchor="w", pady=4)
            return
        for name in names:
            is_sel = name == state["selected"]
            row = ctk.CTkFrame(
                listbox,
                fg_color=("gray75", "gray30") if is_sel else "transparent",
                corner_radius=4,
                cursor="hand2",
            )
            row.pack(fill="x", pady=2)
            lbl = ctk.CTkLabel(row, text=name, anchor="w")
            lbl.pack(fill="x", padx=8, pady=4)
            lbl.bind("<Button-1>", lambda _e, n=name: select(n))
            row.bind("<Button-1>", lambda _e, n=name: select(n))

    def select(name: str):
        state["selected"] = name
        refresh_list()

    def do_new():
        name = simpledialog.askstring("New profile", "Profile name:", parent=d)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if name in profiles.list_profiles():
            messagebox.showerror("New profile", "A profile with that name already exists.", parent=d)
            return
        current = profiles.get_current_profile()
        profiles.save_profile(name, current)
        profiles.set_current_profile(name)
        state["selected"] = name
        refresh_list()
        if on_profiles_changed:
            on_profiles_changed()

    def do_rename():
        sel = state["selected"]
        if not sel:
            messagebox.showinfo("Rename profile", "Select a profile first.", parent=d)
            return
        new_name = simpledialog.askstring("Rename profile", "New profile name:", initialvalue=sel, parent=d)
        if not new_name or new_name.strip() == sel:
            return
        new_name = new_name.strip()
        if new_name in profiles.list_profiles():
            messagebox.showerror("Rename profile", "A profile with that name already exists.", parent=d)
            return
        settings = profiles.load_profile(sel)
        if settings is None:
            return
        # Save under new name then delete old
        profiles.save_profile(new_name, settings)
        profiles.delete_profile(sel)
        profiles.set_current_profile(new_name)
        state["selected"] = new_name
        refresh_list()
        if on_profiles_changed:
            on_profiles_changed()

    def do_delete():
        sel = state["selected"]
        if not sel:
            messagebox.showinfo("Delete profile", "Select a profile first.", parent=d)
            return
        names = profiles.list_profiles()
        if len(names) <= 1:
            messagebox.showwarning("Delete profile", "Cannot delete the last remaining profile.", parent=d)
            return
        if not messagebox.askyesno("Delete profile", f"Delete profile '{sel}'?", parent=d):
            return
        profiles.delete_profile(sel)
        # Ensure there is still a current profile
        remaining = profiles.list_profiles()
        if remaining:
            profiles.set_current_profile(remaining[0])
            state["selected"] = remaining[0]
        else:
            state["selected"] = ""
        refresh_list()
        if on_profiles_changed:
            on_profiles_changed()

    def do_select_and_close():
        sel = state["selected"]
        if sel:
            profiles.set_current_profile(sel)
            if on_profiles_changed:
                on_profiles_changed()
        d.destroy()

    btn_frame = ctk.CTkFrame(main, fg_color="transparent")
    btn_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
    _new_btn = ctk.CTkButton(btn_frame, text="New", width=80, command=do_new)
    _new_btn.pack(side="left", padx=5)
    add_tooltip(_new_btn, "Create a new profile by cloning the current one")
    _rename_btn = ctk.CTkButton(btn_frame, text="Rename", width=80, command=do_rename)
    _rename_btn.pack(side="left", padx=5)
    add_tooltip(_rename_btn, "Rename the selected profile")
    _delete_btn = ctk.CTkButton(btn_frame, text="Delete", width=80, fg_color="darkred", command=do_delete)
    _delete_btn.pack(side="left", padx=5)
    add_tooltip(_delete_btn, "Delete the selected profile (cannot delete the last remaining profile)")
    _set_close_btn = ctk.CTkButton(btn_frame, text="Set current / Close", width=130, command=do_select_and_close)
    _set_close_btn.pack(side="right", padx=5)
    add_tooltip(_set_close_btn, "Make the selected profile active and close this dialog")

    refresh_list()

