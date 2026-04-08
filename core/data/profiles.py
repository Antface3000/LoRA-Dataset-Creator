"""Profiles system for saving/loading user settings.

All settings (Crop Resolution, VLM Prompts, Thresholds) must be savable as JSON Profiles.
"""

import json
from pathlib import Path
from typing import Dict, Optional, List

from core.data.caption_prompt_presets import normalize_library_item, unique_saved_name
from core.config import (
    BUCKET_PORTRAIT, BUCKET_SQUARE, BUCKET_LANDSCAPE,
    MIN_LAPLACIAN_VARIANCE, MIN_AESTHETIC_SCORE,
    DEFAULT_PADDING_MARGIN, DEFAULT_PERSON_CONFIDENCE
)


class ProfilesManager:
    """Manages user settings profiles."""
    
    def __init__(self, config_file: Path = None):
        if config_file is None:
            # Default to flux_prep_config.json in project root
            config_file = Path(__file__).parent.parent.parent / "flux_prep_config.json"
        self.config_file = config_file
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from file."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    self.config = json.load(f)
            except Exception as e:
                print(f"Error loading config: {e}")
                self.config = self._default_config()
        else:
            self.config = self._default_config()
        if "profiles" not in self.config:
            self.config["profiles"] = {}
        if "User settings" not in self.config["profiles"]:
            self.config["profiles"]["User settings"] = self._default_config()["profiles"]["User settings"]
            self._save_config()
        if not self.config.get("current_profile"):
            self.config["current_profile"] = "User settings"
            self._save_config()
        if "caption_prompt_library" not in self.config:
            self.config["caption_prompt_library"] = []
        elif not isinstance(self.config["caption_prompt_library"], list):
            self.config["caption_prompt_library"] = []
    
    def _default_config(self) -> Dict:
        """Get default configuration structure."""
        return {
            "profiles": {
                "User settings": {
                    "bucket_resolutions": {
                        "portrait": list(BUCKET_PORTRAIT),
                        "square": list(BUCKET_SQUARE),
                        "landscape": list(BUCKET_LANDSCAPE)
                    },
                    "quality_thresholds": {
                        "min_laplacian_variance": MIN_LAPLACIAN_VARIANCE,
                        "min_aesthetic_score": MIN_AESTHETIC_SCORE
                    },
                    "vlm_prompt": "Describe this image in detail, focusing on the subject and composition.",
                    "caption_system_prompt": "",
                    "caption_source": "local",
                    "caption_local_model": "joycaption",
                    "ollama_url": "http://localhost:11434",
                    "ollama_model": "llava",
                    "openai_api_key": "",
                    "openai_model": "gpt-4o",
                    "anthropic_api_key": "",
                    "anthropic_model": "claude-3-5-haiku-20241022",
                    "gemini_api_key": "",
                    "gemini_model": "gemini-2.5-flash",
                    "padding_margin": DEFAULT_PADDING_MARGIN,
                    "person_confidence": DEFAULT_PERSON_CONFIDENCE,
                    "ui_scaling": 1.0,
                    "appearance_mode": "dark",
                    "text_scale": 1.0,
                    "default_trigger_words": "",
                    "default_find_replace": [],
                    "default_output_format": "Natural language",
                    "enable_nudenet": False,
                    "color_theme": "blue",
                    "min_crop_px": 512,
                    "master_tag_list_mode": "scanned",
                    "master_tag_pool_not_on_image_only": False,
                }
            },
            "current_profile": "User settings",
            "source_folder": "",
            "output_folder": "",
            "processed_folder": "",
            "caption_prompt_library": [],
        }
    
    def _save_config(self) -> None:
        """Save configuration to file."""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def load_profile(self, name: str) -> Optional[Dict]:
        """Load a profile by name.
        
        Args:
            name: Profile name
        
        Returns:
            Profile settings dict, or None if not found
        """
        profiles = self.config.get("profiles", {})
        return profiles.get(name)
    
    def save_profile(self, name: str, settings: Dict) -> None:
        """Save a profile.
        
        Args:
            name: Profile name
            settings: Profile settings dict
        """
        if "profiles" not in self.config:
            self.config["profiles"] = {}
        
        self.config["profiles"][name] = settings
        self._save_config()
    
    def get_current_profile(self) -> Dict:
        """Get current active profile.
        
        Returns:
            Current profile settings dict
        """
        current_name = self.config.get("current_profile", "User settings")
        profile = self.load_profile(current_name)
        
        if profile is None:
            return self._default_config()["profiles"]["User settings"]
        
        return profile
    
    def set_current_profile(self, name: str) -> None:
        """Set current active profile.
        
        Args:
            name: Profile name
        """
        if name in self.config.get("profiles", {}):
            self.config["current_profile"] = name
            self._save_config()
    
    def list_profiles(self) -> List[str]:
        """List all available profile names.
        
        Returns:
            List of profile names
        """
        return list(self.config.get("profiles", {}).keys())
    
    def delete_profile(self, name: str) -> None:
        """Delete a profile.
        
        Args:
            name: Profile name
        """
        if "profiles" in self.config and name in self.config["profiles"]:
            del self.config["profiles"][name]
            
            # If deleted profile was current, switch to first available
            if self.config.get("current_profile") == name:
                profiles = list(self.config["profiles"].keys())
                if profiles:
                    self.config["current_profile"] = profiles[0]
                else:
                    # Create default if no profiles left
                    self.config = self._default_config()
            
            self._save_config()
    
    def get_folders(self) -> tuple[Optional[str], Optional[str]]:
        """Get saved source and output folders.
        
        Returns:
            (source_folder, output_folder) tuple
        """
        source = self.config.get("source_folder", "")
        output = self.config.get("output_folder", "")
        return source if source else None, output if output else None

    # Caption system prompt helpers

    def get_caption_system_prompt(self) -> Optional[str]:
        """Return the caption system prompt for the current profile, if set."""
        profile = self.get_current_profile()
        prompt = profile.get("caption_system_prompt")
        if isinstance(prompt, str) and prompt.strip():
            return prompt
        return None

    def set_caption_system_prompt(self, prompt: str) -> None:
        """Set and persist the caption system prompt for the current profile."""
        name = self.config.get("current_profile", "User settings")
        profile = self.load_profile(name) or self._default_config()["profiles"]["User settings"]
        profile["caption_system_prompt"] = prompt or ""
        self.save_profile(name, profile)

    def get_caption_prompt_library(self) -> List[Dict[str, str]]:
        """Return user-saved caption presets (name, system, user)."""
        raw = self.config.get("caption_prompt_library", [])
        if not isinstance(raw, list):
            return []
        out: List[Dict[str, str]] = []
        for x in raw:
            n = normalize_library_item(x)
            if n:
                out.append(n)
        return out

    def set_caption_prompt_library(self, items: List[Dict[str, str]]) -> None:
        """Replace the entire saved caption preset list."""
        self.config["caption_prompt_library"] = list(items)
        self._save_config()

    def add_caption_prompt_library_entry(self, name: str, system: str, user: str) -> str:
        """Append a saved preset; returns the final name (deduped if needed)."""
        lib = self.get_caption_prompt_library()
        base = (name or "").strip() or "Untitled"
        final = unique_saved_name(lib, base)
        lib.append({"name": final, "system": system or "", "user": user or ""})
        self.set_caption_prompt_library(lib)
        return final

    def remove_caption_prompt_library_entry(self, name: str) -> bool:
        """Remove a saved preset by exact name. Returns True if something was removed."""
        lib = self.get_caption_prompt_library()
        new = [x for x in lib if x["name"] != name]
        if len(new) == len(lib):
            return False
        self.set_caption_prompt_library(new)
        return True

    # Caption backend helpers

    _CAPTION_BACKEND_KEYS = [
        "caption_source", "caption_local_model",
        "ollama_url", "ollama_model",
        "openai_api_key", "openai_model",
        "anthropic_api_key", "anthropic_model",
        "gemini_api_key", "gemini_model",
    ]

    def get_caption_backend_settings(self) -> Dict:
        """Return caption backend fields from the current profile."""
        profile = self.get_current_profile()
        defaults = self._default_config()["profiles"]["User settings"]
        return {k: profile.get(k, defaults.get(k, "")) for k in self._CAPTION_BACKEND_KEYS}

    def set_caption_backend_settings(self, settings: Dict) -> None:
        """Persist caption backend fields to the current profile."""
        name = self.config.get("current_profile", "User settings")
        profile = self.load_profile(name) or self._default_config()["profiles"]["User settings"]
        for k in self._CAPTION_BACKEND_KEYS:
            if k in settings:
                profile[k] = settings[k]
        self.save_profile(name, profile)

    def get_processed_folder(self) -> Optional[str]:
        """Get saved processed folder (empty = use source_folder/processed)."""
        p = self.config.get("processed_folder", "")
        return p if p else None

    def set_folders(self, source_folder: Optional[str], output_folder: Optional[str],
                    processed_folder: Optional[str] = None) -> None:
        """Set source, output, and optional processed folders.
        
        Args:
            source_folder: Source folder path
            output_folder: Output folder path
            processed_folder: Processed folder path (None = leave unchanged; "" = use source/processed)
        """
        if source_folder:
            self.config["source_folder"] = source_folder
        if output_folder:
            self.config["output_folder"] = output_folder
        if processed_folder is not None:
            self.config["processed_folder"] = processed_folder
        self._save_config()


# Global singleton instance
_profiles_manager: Optional[ProfilesManager] = None


def get_profiles_manager(config_file: Path = None) -> ProfilesManager:
    """Get the global profiles manager instance.
    
    Args:
        config_file: Optional config file path
    
    Returns:
        ProfilesManager instance
    """
    global _profiles_manager
    if _profiles_manager is None:
        _profiles_manager = ProfilesManager(config_file)
    return _profiles_manager
