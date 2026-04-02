"""ImageCard component - displays image with aesthetic score overlay."""

import customtkinter as ctk
from pathlib import Path
from PIL import Image, ImageTk, ImageDraw, ImageFont
from typing import Optional, Callable


class ImageCard(ctk.CTkFrame):
    """Image card widget with aesthetic score overlay."""
    
    def __init__(
        self,
        parent,
        image_path: Path,
        aesthetic_score: Optional[float] = None,
        width: int = 200,
        height: int = 200,
        command: Optional[Callable] = None
    ):
        super().__init__(parent, width=width, height=height)
        
        self.image_path = image_path
        self.aesthetic_score = aesthetic_score
        self.command = command
        
        # Load and resize image
        self._load_image()
        
        # Create label for image
        self.image_label = ctk.CTkLabel(
            self,
            image=self.photo_image,
            text="",
            cursor="hand2" if command else "arrow"
        )
        self.image_label.pack(fill="both", expand=True)
        
        # Bind click event
        if command:
            self.image_label.bind("<Button-1>", lambda e: command())
            self.bind("<Button-1>", lambda e: command())
    
    def _load_image(self) -> None:
        """Load and prepare image with score overlay."""
        try:
            # Load image
            image = Image.open(self.image_path)
            
            # Calculate thumbnail size maintaining aspect ratio
            target_width = 200
            target_height = 200
            
            # Resize maintaining aspect ratio
            image.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
            
            # Create overlay with score if available
            if self.aesthetic_score is not None:
                overlay = image.copy().convert("RGBA")
                draw = ImageDraw.Draw(overlay)
                
                # Score text
                score_text = f"{self.aesthetic_score:.1f}"
                
                # Determine color based on score
                if self.aesthetic_score < 5:
                    color = (255, 0, 0, 255)  # Red
                elif self.aesthetic_score < 7:
                    color = (255, 255, 0, 255)  # Yellow
                else:
                    color = (0, 255, 0, 255)  # Green
                
                # Draw background rectangle for text
                try:
                    font = ImageFont.truetype("arial.ttf", 16)
                except:
                    font = ImageFont.load_default()
                
                # Get text bounding box
                bbox = draw.textbbox((0, 0), score_text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                
                # Draw background
                padding = 4
                rect_coords = [
                    overlay.width - text_width - padding * 2 - 2,
                    2,
                    overlay.width - 2,
                    text_height + padding * 2 + 2
                ]
                draw.rectangle(rect_coords, fill=(0, 0, 0, 200))  # Semi-transparent black
                
                # Draw text
                text_pos = (
                    overlay.width - text_width - padding - 2,
                    padding + 2
                )
                draw.text(text_pos, score_text, fill=color, font=font)
                
                # Composite overlay onto image
                image = Image.alpha_composite(
                    image.convert("RGBA"),
                    overlay
                ).convert("RGB")
            
            # Convert to PhotoImage
            self.photo_image = ImageTk.PhotoImage(image)
        except Exception as e:
            print(f"Error loading image {self.image_path}: {e}")
            # Create placeholder
            placeholder = Image.new("RGB", (200, 200), color=(128, 128, 128))
            self.photo_image = ImageTk.PhotoImage(placeholder)
    
    def update_score(self, score: float) -> None:
        """Update aesthetic score and refresh display.
        
        Args:
            score: New aesthetic score
        """
        self.aesthetic_score = score
        self._load_image()
        self.image_label.configure(image=self.photo_image)
