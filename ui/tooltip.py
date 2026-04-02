"""Shared tooltip utility for the LoRA Dataset Manager UI."""

import tkinter as tk


class ToolTip:
    """Show a small floating label when the mouse hovers over a widget."""

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self._tip = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event=None):
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self._tip,
            text=self.text,
            background="#2b2b2b",
            foreground="white",
            relief="solid",
            borderwidth=1,
            font=("TkDefaultFont", 9),
            wraplength=260,
            justify="left",
            padx=5,
            pady=3,
        ).pack()

    def _hide(self, _event=None):
        if self._tip:
            self._tip.destroy()
            self._tip = None


def add_tooltip(widget, text: str) -> ToolTip:
    """Attach a hover tooltip to *widget* showing *text*."""
    return ToolTip(widget, text)
