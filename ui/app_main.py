"""Main Application Window - Wizard flow with profile and drag-drop."""

import customtkinter as ctk
from pathlib import Path

from core.pipeline_manager import get_pipeline_manager
from core.data.profiles import get_profiles_manager
from core.session import get_session
from core.ai.vram import get_vram_manager, State
from ui.wizard.steps import StepDirectories, StepImages, StepCaptions, StepFinalize
from ui.settings_dialog import open_settings_dialog
from ui.profile_manager_dialog import open_profile_manager
from ui.tabs.tab_batch_rename import TabBatchRename
from ui.tabs.tab_sort import SortTab
from ui.tooltip import add_tooltip
from ui.tutorial_dialog import open_tutorial_dialog

# Native drag-drop disabled: the ctypes window-proc subclass caused access violations
# on Windows. Use the Browse buttons on each step instead.


class App:
    """Main application: wizard (Directories → Images → Tags/Captions → Finalize)."""

    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.pipeline_manager = get_pipeline_manager()
        self.profiles_manager = get_profiles_manager()
        self.session = get_session()
        profile = self.profiles_manager.get_current_profile()
        scale = float(profile.get("ui_scaling", 1.0))
        ctk.set_widget_scaling(scale)
        ctk.set_window_scaling(scale)
        ctk.set_appearance_mode(profile.get("appearance_mode", "dark"))
        self.root = ctk.CTk()
        self.root.title("LoRA Dataset Manager")
        self.root.minsize(1050, 650)
        self.root.geometry("1280x860")
        self.root.after(100, lambda: self.root.geometry("1280x860"))
        self.current_step = 0
        self.step_frames = []
        self.step_names = ["Directories", "Images", "Tags & Captions", "Finalize"]
        self._caption_models_prewarmed = False
        self.setup_ui()
        self.load_profile_settings()
        self._show_step(0)
        global _app
        _app = self

    def setup_ui(self):
        menu_frame = ctk.CTkFrame(self.root)
        menu_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(menu_frame, text="LoRA Dataset Manager", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=10)
        ctk.CTkLabel(menu_frame, text="Profile:").pack(side="left", padx=5)
        current = self.profiles_manager.config.get("current_profile", "User settings")
        self.profile_var = ctk.StringVar(value=current)
        self.profile_menu = ctk.CTkOptionMenu(
            menu_frame,
            variable=self.profile_var,
            values=self.profiles_manager.list_profiles(),
            command=self.on_profile_change
        )
        self.profile_menu.pack(side="left", padx=5)
        add_tooltip(self.profile_menu, "Switch the active settings profile")
        _manage_btn = ctk.CTkButton(menu_frame, text="Manage…", width=80, command=self._open_profile_manager)
        _manage_btn.pack(side="left", padx=(5, 0))
        add_tooltip(_manage_btn, "Create, rename, or delete profiles")
        _settings_btn = ctk.CTkButton(menu_frame, text="Settings", width=80, command=self._open_settings)
        _settings_btn.pack(side="left", padx=(15, 0))
        add_tooltip(_settings_btn, "Open application settings for the current profile")
        _tutorial_btn = ctk.CTkButton(menu_frame, text="?", width=36, command=self._open_tutorial)
        _tutorial_btn.pack(side="left", padx=(5, 0))
        add_tooltip(_tutorial_btn, "Open the getting-started tutorial")
        step_font_size = max(10, int(12 * self.get_text_scale()))
        self.step_label = ctk.CTkLabel(menu_frame, text="Step 1 of 4 – Directories", font=ctk.CTkFont(size=step_font_size))
        # hidden until the Wizard tab is active
        self.step_label.pack_forget()

        self.tabview = ctk.CTkTabview(self.root, width=900, command=self._on_tab_changed)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=(0, 0))

        # Global status bar — always visible at the bottom of the window
        status_bar = ctk.CTkFrame(self.root, height=28, corner_radius=0)
        status_bar.pack(fill="x", side="bottom", padx=0, pady=0)
        status_bar.pack_propagate(False)
        self._status_progress = ctk.CTkProgressBar(status_bar, width=140, height=10, mode="indeterminate")
        self._status_progress.pack(side="left", padx=(10, 6), pady=9)
        self._status_progress.set(0)
        self._status_label = ctk.CTkLabel(status_bar, text="Ready", text_color="gray70", anchor="w")
        self._status_label.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.tabview.add("Batch rename (WD14)")
        self.tabview.add("Crop & Sort")
        self.tabview.add("Wizard")

        wizard_tab = self.tabview.tab("Wizard")
        wizard_tab.grid_columnconfigure(0, weight=1)
        wizard_tab.grid_rowconfigure(1, weight=1)
        self.wizard_content = ctk.CTkFrame(wizard_tab, fg_color="transparent")
        self.wizard_content.grid(row=1, column=0, sticky="nsew", padx=0, pady=5)
        self.wizard_content.grid_columnconfigure(0, weight=1)
        self.wizard_content.grid_rowconfigure(0, weight=1)
        step1 = StepDirectories(self.wizard_content, on_paths_changed=lambda: None)
        step2 = StepImages(self.wizard_content, on_list_changed=lambda: self._refresh_finalize_summary())
        step3 = StepCaptions(self.wizard_content, on_changed=lambda: None)
        step4 = StepFinalize(self.wizard_content, on_finalize_done=lambda: self._refresh_finalize_summary())
        for f in (step1, step2, step3, step4):
            f.grid(row=0, column=0, sticky="nsew")
            self.step_frames.append(f)
        nav = ctk.CTkFrame(wizard_tab, fg_color="transparent")
        nav.grid(row=2, column=0, sticky="ew", padx=0, pady=(0, 10))
        wizard_tab.grid_columnconfigure(0, weight=1)
        _back_btn = ctk.CTkButton(nav, text="Back", width=80, command=self._back)
        _back_btn.pack(side="left", padx=5)
        add_tooltip(_back_btn, "Go to the previous wizard step")
        self.next_btn = ctk.CTkButton(nav, text="Next", width=80, command=self._next)
        self.next_btn.pack(side="left", padx=5)
        add_tooltip(self.next_btn, "Advance to the next step / write output files on the final step")

        crop_tab = self.tabview.tab("Crop & Sort")
        crop_tab.grid_columnconfigure(0, weight=1)
        crop_tab.grid_rowconfigure(0, weight=1)
        self._sort_tab = SortTab(crop_tab, on_back=lambda: self.tabview.set("Wizard"))
        self._sort_tab.grid(row=0, column=0, sticky="nsew")

        batch_tab = self.tabview.tab("Batch rename (WD14)")
        batch_tab.grid_columnconfigure(0, weight=1)
        batch_tab.grid_rowconfigure(0, weight=1)
        TabBatchRename(batch_tab).grid(row=0, column=0, sticky="nsew")

    def _import_crop_queue_into_session(self):
        """Pull any paths the Crop & Sort tab queued into the wizard session."""
        queue = list(self.pipeline_manager.caption_queue)
        if not queue:
            return
        self.pipeline_manager.caption_queue.clear()
        added = self.session.add_items(queue)
        if added and hasattr(self.step_frames[1], "_refresh_list"):
            self.step_frames[1]._refresh_list()

    def _show_step(self, step: int):
        self.current_step = step
        for i, f in enumerate(self.step_frames):
            f.grid_remove() if i != step else f.grid()
        self.step_label.configure(text=f"Step {step + 1} of 4 – {self.step_names[step]}")
        if step == 3:
            self.next_btn.configure(text="Finalize", command=self._finalize_click)
            self.step_frames[3].refresh_summary()
        else:
            self.next_btn.configure(text="Next", command=self._next)
        vram = get_vram_manager()
        if step == 2:
            vram.ensure_state(State.CAPTIONING)
            if not self._caption_models_prewarmed:
                vram.prewarm_captioning_models()
                self._caption_models_prewarmed = True
        else:
            vram.ensure_state(State.IDLE)
        if step == 1:
            self._import_crop_queue_into_session()

    def _on_tab_changed(self):
        """Called whenever the user clicks a main tab."""
        tab = self.tabview.get()
        if tab == "Wizard":
            self.step_label.pack(side="left", padx=20)
            self._show_step(0)
        else:
            self.step_label.pack_forget()

        if tab == "Crop & Sort":
            # If the sort tab has an image list ready but hasn't loaded
            # the first image yet (e.g. after a profile load), kick it off now.
            if (hasattr(self, "_sort_tab")
                    and self._sort_tab.image_files
                    and self._sort_tab.original_image is None):
                self._sort_tab.load_current_image()

    def _back(self):
        if self.current_step > 0:
            if self.current_step == 2 and hasattr(self.step_frames[2], "on_leave"):
                self.step_frames[2].on_leave()
            self._show_step(self.current_step - 1)

    def _next(self):
        if self.current_step < 3:
            if self.current_step == 2 and hasattr(self.step_frames[2], "on_leave"):
                self.step_frames[2].on_leave()
            self._show_step(self.current_step + 1)

    def _finalize_click(self):
        self.step_frames[3]._finalize()

    def _refresh_finalize_summary(self):
        if self.current_step == 3 and hasattr(self.step_frames[3], "refresh_summary"):
            self.step_frames[3].refresh_summary()

    def _on_drop(self, paths):
        if not paths:
            return
        paths = [Path(p) for p in paths]
        step = self.step_frames[self.current_step]
        if hasattr(step, "on_drop") and step.on_drop(paths):
            return
        if self.current_step == 0:
            self.step_frames[0].on_drop(paths)
        elif self.current_step == 1:
            self.step_frames[1].on_drop(paths)

    def _open_settings(self):
        # Remember current step so Settings doesn't jump the wizard.
        saved_step = self.current_step
        def _on_applied():
            self._apply_ui_from_profile()
            # Reload profile-dependent settings but keep the same wizard step.
            self.load_profile_settings()
            self._show_step(saved_step)
        open_settings_dialog(self.root, on_applied_callback=_on_applied)

    def _open_tutorial(self):
        open_tutorial_dialog(self.root)

    def _open_profile_manager(self):
        """Open profile manager and refresh dropdown + settings when done."""
        def _on_changed():
            # Reload profile names and current selection
            names = self.profiles_manager.list_profiles()
            self.profile_menu.configure(values=names)
            current = self.profiles_manager.config.get("current_profile", "User settings")
            self.profile_var.set(current)
            self.load_profile_settings()
        open_profile_manager(self.root, on_profiles_changed=_on_changed)

    def _apply_ui_from_profile(self):
        """Apply appearance and scaling from current profile."""
        profile = self.profiles_manager.get_current_profile()
        mode = profile.get("appearance_mode", "dark")
        scale = float(profile.get("ui_scaling", 1.0))
        ctk.set_appearance_mode(mode)
        ctk.set_widget_scaling(scale)
        ctk.set_window_scaling(scale)
        step_font_size = max(10, int(12 * self.get_text_scale()))
        self.step_label.configure(font=ctk.CTkFont(size=step_font_size))

    @staticmethod
    def get_text_scale() -> float:
        """Return text scale factor from current profile (for accessibility). 1.0 = 100%."""
        return float(get_profiles_manager().get_current_profile().get("text_scale", 1.0))

    def on_profile_change(self, profile_name: str):
        self.profiles_manager.set_current_profile(profile_name)
        self.load_profile_settings()

    def load_profile_settings(self):
        profile = self.profiles_manager.get_current_profile()
        self._apply_ui_from_profile()
        source_folder, output_folder = self.profiles_manager.get_folders()
        if source_folder:
            p = Path(source_folder)
            self.session.source_folder = p
            self.session.processed_folder = p / "processed"
            self.pipeline_manager.source_folder = p
        if output_folder:
            p = Path(output_folder)
            self.session.output_folder = p
            self.pipeline_manager.output_folder = p
        processed = self.profiles_manager.get_processed_folder()
        if processed:
            self.session.processed_folder = Path(processed)
        if hasattr(self, "step_frames") and len(self.step_frames) >= 1:
            if hasattr(self.step_frames[0], "_refresh_labels"):
                self.step_frames[0]._refresh_labels()
        if hasattr(self, "step_frames") and len(self.step_frames) >= 2:
            if hasattr(self.step_frames[1], "_refresh_list"):
                self.step_frames[1]._refresh_list()
        if hasattr(self, "step_frames") and len(self.step_frames) >= 3:
            if hasattr(self.step_frames[2], "apply_profile"):
                self.step_frames[2].apply_profile(profile)
        if hasattr(self, "_sort_tab"):
            self._sort_tab.apply_profile(profile)
            self._sort_tab.apply_nudenet_visibility()
            # Sync source/output folders so the tab can work without the user
            # having to re-select them manually after loading a profile.
            from core.data.file_handler import load_image_files
            pm_src = self.pipeline_manager.source_folder
            pm_out = self.pipeline_manager.output_folder
            if pm_out:
                self._sort_tab.output_folder = pm_out
            if pm_src and pm_src.exists():
                if self._sort_tab.source_folder != pm_src:
                    self._sort_tab.source_folder = pm_src
                    all_files = load_image_files(pm_src)
                    self._sort_tab.image_files = self._sort_tab._get_remaining_files(all_files)
                    self._sort_tab.current_index = 0
        # Refresh finalize summary only if we're on the finalize step.
        self._refresh_finalize_summary()

    def set_global_status(self, message: str, busy: bool = False):
        """Update the global status bar. Call from any thread via root.after(0, ...)."""
        self._status_label.configure(text=message)
        if busy:
            self._status_progress.configure(mode="indeterminate")
            self._status_progress.start()
        else:
            self._status_progress.stop()
            self._status_progress.configure(mode="determinate")
            self._status_progress.set(0)

    def set_global_progress(self, current: int, total: int, message: str = ""):
        """Show a determinate progress bar (current/total) with optional message."""
        fraction = current / total if total > 0 else 0
        self._status_progress.stop()
        self._status_progress.configure(mode="determinate")
        self._status_progress.set(fraction)
        label = message or f"{current}/{total}"
        self._status_label.configure(text=label)

    def run(self):
        self.root.mainloop()


# Module-level singleton reference — set once App() is constructed
_app: "App | None" = None


def get_app() -> "App | None":
    return _app


def set_status(message: str, busy: bool = False):
    """Thread-safe global status update callable from any module."""
    app = get_app()
    if app is None:
        return
    app.root.after(0, lambda: app.set_global_status(message, busy))


def set_progress(current: int, total: int, message: str = ""):
    """Thread-safe determinate progress update callable from any module."""
    app = get_app()
    if app is None:
        return
    app.root.after(0, lambda: app.set_global_progress(current, total, message))


def main():
    global _app
    _app = App()
    _app.run()


if __name__ == "__main__":
    main()
