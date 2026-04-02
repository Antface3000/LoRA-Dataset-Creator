"""TagChip component - editable tag widget for caption editor."""

import customtkinter as ctk
from typing import Optional, Callable


class TagChip(ctk.CTkFrame):
    """Tag chip widget with remove button."""
    
    def __init__(
        self,
        parent,
        tag_text: str,
        on_remove: Optional[Callable[[str], None]] = None,
        on_click: Optional[Callable[[str], None]] = None
    ):
        super().__init__(parent)
        
        self.tag_text = tag_text
        self.on_remove = on_remove
        self.on_click = on_click
        
        # Tag label
        self.tag_label = ctk.CTkLabel(
            self,
            text=tag_text,
            font=ctk.CTkFont(size=12),
            cursor="hand2" if on_click else "arrow"
        )
        self.tag_label.pack(side="left", padx=(8, 4), pady=4)
        
        # Remove button
        if on_remove:
            self.remove_button = ctk.CTkButton(
                self,
                text="×",
                width=20,
                height=20,
                font=ctk.CTkFont(size=14, weight="bold"),
                fg_color="transparent",
                hover_color="#f44336",
                command=lambda: on_remove(tag_text)
            )
            self.remove_button.pack(side="left", padx=(0, 4), pady=4)
        
        # Bind click event
        if on_click:
            self.tag_label.bind("<Button-1>", lambda e: on_click(tag_text))
            self.bind("<Button-1>", lambda e: on_click(tag_text))
    
    def get_text(self) -> str:
        """Get tag text.
        
        Returns:
            Tag text string
        """
        return self.tag_text
