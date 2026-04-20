"""Main application window: main tabs include session steps (Directories → Finalize)."""

import customtkinter as ctk
from pathlib import Path

from core.pipeline_manager import get_pipeline_manager
from core.data.profiles import get_profiles_manager
from core.session import get_session
from core.session_autosave import (
    apply_session_dict,
    delete_autosave_file,
    load_session_snapshot,
    save_session_snapshot,
)
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

TAB_BATCH = "Batch rename (WD14)"
TAB_CROP = "Crop & Sort"
TAB_DIRS = "Directories"
TAB_IMAGES = "Images"
TAB_TAGS = "Tags & Captions"
TAB_FINALIZE = "Finalize"
MAIN_TAB_LABELS = frozenset(
    {TAB_BATCH, TAB_CROP, TAB_DIRS, TAB_IMAGES, TAB_TAGS, TAB_FINALIZE}
)


class App:
    """Main application: session workflow as top-level tabs plus Crop & Sort and batch rename."""

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
        ctk.set_default_color_theme(profile.get("color_theme", "blue"))
        self.root = ctk.CTk()
        self.root.title("LoRA Dataset Manager")
        self.root.minsize(1050, 650)
        self.root.geometry("1280x860")
        self.root.after(100, lambda: self.root.geometry("1280x860"))
        self.step_frames = []
        self._caption_models_prewarmed = False
        self._session_autosave_after_id: int | None = None
        self._pending_restore_tab: str | None = None
        self._previous_main_tab: str | None = None
        self.setup_ui()
        self.load_profile_settings()
        self._restore_wizard_session_from_autosave()
        self._apply_initial_main_tab_selection()
        self.root.protocol("WM_DELETE_WINDOW", self._on_app_close)
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

        self.tabview.add(TAB_BATCH)
        self.tabview.add(TAB_CROP)
        self.tabview.add(TAB_DIRS)
        self.tabview.add(TAB_IMAGES)
        self.tabview.add(TAB_TAGS)
        self.tabview.add(TAB_FINALIZE)

        def _prep_tab(name: str) -> ctk.CTkFrame:
            t = self.tabview.tab(name)
            t.grid_columnconfigure(0, weight=1)
            t.grid_rowconfigure(0, weight=1)
            return t

        dirs_tab = _prep_tab(TAB_DIRS)
        images_tab = _prep_tab(TAB_IMAGES)
        tags_tab = _prep_tab(TAB_TAGS)
        finalize_tab = _prep_tab(TAB_FINALIZE)

        step1 = StepDirectories(dirs_tab, on_paths_changed=self.schedule_wizard_session_autosave)
        step2 = StepImages(
            images_tab,
            on_list_changed=self._on_step2_list_changed,
            on_clear_session=self._clear_wizard_session_ui,
        )
        step3 = StepCaptions(
            tags_tab,
            on_changed=self._on_step3_changed,
            open_settings_cb=self._open_settings,
        )
        step4 = StepFinalize(finalize_tab, on_finalize_done=lambda: self._refresh_finalize_summary())
        step1.grid(row=0, column=0, sticky="nsew")
        step2.grid(row=0, column=0, sticky="nsew")
        step3.grid(row=0, column=0, sticky="nsew")
        step4.grid(row=0, column=0, sticky="nsew")
        self.step_frames.extend([step1, step2, step3, step4])

        crop_tab = _prep_tab(TAB_CROP)
        self._sort_tab = SortTab(crop_tab, on_back=lambda: self.tabview.set(TAB_IMAGES))
        self._sort_tab.grid(row=0, column=0, sticky="nsew")

        batch_tab = _prep_tab(TAB_BATCH)
        TabBatchRename(batch_tab).grid(row=0, column=0, sticky="nsew")

    def _apply_initial_main_tab_selection(self) -> None:
        target = self._pending_restore_tab
        if not isinstance(target, str) or target not in MAIN_TAB_LABELS:
            target = TAB_DIRS
        before = self.tabview.get()
        self.tabview.set(target)
        # CTkTabview.set does not invoke command; apply tab side effects explicitly.
        self._handle_main_tab_changed(before, target)
        self._previous_main_tab = target

    def _import_crop_queue_into_session(self):
        """Pull any paths the Crop & Sort tab queued into the wizard session."""
        queue = list(self.pipeline_manager.caption_queue)
        if not queue:
            return
        self.pipeline_manager.caption_queue.clear()
        added = self.session.add_items(queue)
        if added:
            if hasattr(self.step_frames[1], "_refresh_list"):
                self.step_frames[1]._refresh_list()
            if len(self.step_frames) >= 3 and hasattr(self.step_frames[2], "_refresh_list"):
                self.step_frames[2]._refresh_list()
        self.schedule_wizard_session_autosave()

    def schedule_wizard_session_autosave(self) -> None:
        """Debounced write of wizard session to wizard_session_autosave.json."""
        if self._session_autosave_after_id is not None:
            try:
                self.root.after_cancel(self._session_autosave_after_id)
            except Exception:
                pass
            self._session_autosave_after_id = None
        self._session_autosave_after_id = self.root.after(450, self._flush_wizard_session_autosave)

    def _flush_wizard_session_autosave(self) -> None:
        self._session_autosave_after_id = None
        idx: int | None = None
        if hasattr(self, "step_frames") and len(self.step_frames) >= 3:
            s3 = self.step_frames[2]
            idx = getattr(s3, "_selected_index_caption", None)
        try:
            save_session_snapshot(
                self.session,
                caption_selected_index=idx,
                active_main_tab=self.tabview.get(),
            )
        except Exception:
            pass

    def _on_step2_list_changed(self) -> None:
        self._refresh_finalize_summary()
        self.schedule_wizard_session_autosave()

    def _on_step3_changed(self) -> None:
        self.schedule_wizard_session_autosave()

    def _restore_wizard_session_from_autosave(self) -> None:
        self._pending_restore_tab = None
        data = load_session_snapshot()
        if not data or not isinstance(data.get("items"), list):
            return
        skipped, n = apply_session_dict(self.session, data)
        raw_tab = data.get("active_main_tab")
        if isinstance(raw_tab, str) and raw_tab in MAIN_TAB_LABELS:
            self._pending_restore_tab = raw_tab
        if self.session.source_folder:
            self.pipeline_manager.source_folder = self.session.source_folder
        if self.session.output_folder:
            self.pipeline_manager.output_folder = self.session.output_folder
        from core.data.file_handler import load_image_files

        if hasattr(self, "step_frames") and len(self.step_frames) >= 1:
            if hasattr(self.step_frames[0], "_refresh_labels"):
                self.step_frames[0]._refresh_labels()
        if hasattr(self, "_sort_tab"):
            pm_src = self.pipeline_manager.source_folder
            pm_out = self.pipeline_manager.output_folder
            if pm_out:
                self._sort_tab.output_folder = pm_out
            if pm_src and pm_src.exists():
                self._sort_tab.source_folder = pm_src
                all_files = load_image_files(pm_src)
                self._sort_tab.image_files = self._sort_tab._get_remaining_files(all_files)
                self._sort_tab.current_index = 0
        if hasattr(self, "step_frames") and len(self.step_frames) >= 3:
            s3 = self.step_frames[2]
            fmt = self.session.get_output_format()
            if fmt in ("Tags only", "Natural language", "Both"):
                s3.output_format_var.set(fmt)
            raw_idx = data.get("caption_selected_index")
            if self.session.items:
                sel = raw_idx if isinstance(raw_idx, int) else 0
                if sel < 0 or sel >= len(self.session.items):
                    sel = 0
                s3.current_index = sel
                s3._selected_index_caption = sel
                s3.index_var.set(str(sel + 1))
            else:
                s3.current_index = None
                s3._selected_index_caption = None
                s3.index_var.set("1")
        if hasattr(self, "step_frames") and len(self.step_frames) >= 2:
            self.step_frames[1]._selected_indices = set()
            if hasattr(self.step_frames[1], "_refresh_list"):
                self.step_frames[1]._refresh_list()
        if hasattr(self, "step_frames") and len(self.step_frames) >= 3:
            self.step_frames[2]._refresh_list()
            self.step_frames[2]._load_current_from_session()
        self._refresh_finalize_summary()
        if skipped and n == 0:
            self.set_global_status(
                f"Session draft: {skipped} image(s) from the save file were skipped (not found on disk).",
                busy=False,
            )
        elif skipped:
            self.set_global_status(
                f"Restored session: {n} image(s) ({skipped} missing from disk skipped).",
                busy=False,
            )
        elif n:
            self.set_global_status(f"Restored session: {n} image(s).", busy=False)

    def _on_app_close(self) -> None:
        if self._session_autosave_after_id is not None:
            try:
                self.root.after_cancel(self._session_autosave_after_id)
            except Exception:
                pass
            self._session_autosave_after_id = None
        idx: int | None = None
        if hasattr(self, "step_frames") and len(self.step_frames) >= 3:
            s3 = self.step_frames[2]
            idx = getattr(s3, "_selected_index_caption", None)
        try:
            save_session_snapshot(
                self.session,
                caption_selected_index=idx,
                active_main_tab=self.tabview.get(),
            )
        except Exception:
            pass
        self.root.destroy()

    def _clear_wizard_session_ui(self) -> None:
        self.session.clear()
        delete_autosave_file()
        if hasattr(self, "step_frames") and len(self.step_frames) >= 2:
            self.step_frames[1]._selected_indices = set()
            if hasattr(self.step_frames[1], "_refresh_list"):
                self.step_frames[1]._refresh_list()
        if hasattr(self, "step_frames") and len(self.step_frames) >= 3:
            s3 = self.step_frames[2]
            s3.current_index = None
            s3._selected_index_caption = None
            s3.index_var.set("1")
            if hasattr(s3, "caption_text"):
                s3.caption_text.delete("1.0", "end")
            s3._refresh_list()
        self._refresh_finalize_summary()

    def _handle_main_tab_changed(self, previous: str | None, current: str) -> None:
        if previous == TAB_TAGS and current != TAB_TAGS:
            if len(self.step_frames) >= 3 and hasattr(self.step_frames[2], "on_leave"):
                self.step_frames[2].on_leave()

        vram = get_vram_manager()
        if current == TAB_TAGS:
            vram.ensure_state(State.CAPTIONING)
            if not self._caption_models_prewarmed:
                vram.prewarm_captioning_models()
                self._caption_models_prewarmed = True
            if len(self.step_frames) >= 3 and hasattr(self.step_frames[2], "_refresh_list"):
                self.step_frames[2]._refresh_list()
        else:
            vram.ensure_state(State.IDLE)

        if current == TAB_IMAGES:
            self._import_crop_queue_into_session()
        if current == TAB_FINALIZE and len(self.step_frames) >= 4 and hasattr(self.step_frames[3], "refresh_summary"):
            self.step_frames[3].refresh_summary()

        if current == TAB_CROP:
            if (hasattr(self, "_sort_tab")
                    and self._sort_tab.image_files
                    and self._sort_tab.original_image is None):
                self._sort_tab.load_current_image()

    def _on_tab_changed(self):
        """Called whenever the user selects a main tab."""
        current = self.tabview.get()
        previous = self._previous_main_tab
        self._handle_main_tab_changed(previous, current)
        self._previous_main_tab = current

    def _refresh_finalize_summary(self):
        if self.tabview.get() == TAB_FINALIZE and len(self.step_frames) >= 4 and hasattr(self.step_frames[3], "refresh_summary"):
            self.step_frames[3].refresh_summary()

    def _on_drop(self, paths):
        if not paths:
            return
        paths = [Path(p) for p in paths]
        tab = self.tabview.get()
        if tab == TAB_DIRS:
            step = self.step_frames[0]
            if hasattr(step, "on_drop") and step.on_drop(paths):
                return
            step.on_drop(paths)
        elif tab == TAB_IMAGES:
            step = self.step_frames[1]
            if hasattr(step, "on_drop") and step.on_drop(paths):
                return
            step.on_drop(paths)

    def _open_settings(self):
        saved_tab = self.tabview.get()

        def _on_applied():
            self._apply_ui_from_profile()
            self.load_profile_settings()
            self.tabview.set(saved_tab)
            prev = self._previous_main_tab
            self._handle_main_tab_changed(prev, self.tabview.get())
            self._previous_main_tab = self.tabview.get()

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
        """Apply appearance, scaling, and color theme from current profile."""
        profile = self.profiles_manager.get_current_profile()
        mode = profile.get("appearance_mode", "dark")
        scale = float(profile.get("ui_scaling", 1.0))
        ctk.set_appearance_mode(mode)
        ctk.set_widget_scaling(scale)
        ctk.set_window_scaling(scale)
        ctk.set_default_color_theme(profile.get("color_theme", "blue"))

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
            if hasattr(self.step_frames[2], "_refresh_list"):
                self.step_frames[2]._refresh_list()
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
