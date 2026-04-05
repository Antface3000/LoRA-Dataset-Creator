"""Caption backend abstraction.

Provides a unified interface for generating captions via multiple sources:
  - local: HuggingFace transformers models (JoyCaption, Florence2, Gemma3)
  - ollama: Ollama local server
  - openai: OpenAI API (GPT-4o, GPT-4 Vision, etc.)
  - anthropic: Anthropic Claude API
  - gemini: Google Gemini API

Usage
-----
    from core.ai.caption_backends import get_caption_backend
    backend = get_caption_backend(profile)
    caption = backend.generate(image_path, tags=["1girl", "solo"], prompt="Describe …")
"""

from __future__ import annotations

import base64
import io
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from PIL import Image

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class CaptionBackend(ABC):
    """Abstract caption backend."""

    @abstractmethod
    def generate(
        self,
        image_path: Path,
        tags: Optional[List[str]] = None,
        prompt: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Generate a caption for *image_path*.

        Parameters
        ----------
        image_path:
            Path to the image file.
        tags:
            Optional list of WD14 tags to include in the prompt context.
        prompt:
            User/instruction prompt override.
        system_prompt:
            System prompt override.

        Returns
        -------
        str
            The generated caption (may be empty string on failure).
        """

    def _encode_image_b64(self, image_path: Path, max_size: int = 1024) -> str:
        """Return a base-64 encoded JPEG of the image (resized to fit *max_size*)."""
        img = Image.open(image_path).convert("RGB")
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _build_user_text(
        self, tags: Optional[List[str]], prompt: Optional[str]
    ) -> str:
        parts: List[str] = []
        if tags:
            parts.append("Tags: " + ", ".join(tags))
        parts.append(
            prompt
            or "Describe this image in detail, focusing on the subject, composition, and style."
        )
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Local transformers backend (delegates to existing captioner.py logic)
# ---------------------------------------------------------------------------

class LocalModelBackend(CaptionBackend):
    """Use one of the local HuggingFace models (JoyCaption, Florence2, Gemma3)."""

    def __init__(self, model_name: str = "joycaption"):
        """
        Parameters
        ----------
        model_name:
            One of ``"joycaption"``, ``"florence2"``, ``"gemma3"``.
        """
        self.model_name = model_name.lower()

    def generate(
        self,
        image_path: Path,
        tags: Optional[List[str]] = None,
        prompt: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        try:
            from core.ai.captioner import generate_caption as _generate
            return _generate(
                image_path,
                tags=tags or [],
                model_override=self.model_name,
                prompt_override=prompt,
                system_prompt_override=system_prompt,
            )
        except Exception as exc:
            logger.error("LocalModelBackend.generate failed: %s", exc)
            return ""


# ---------------------------------------------------------------------------
# Ollama backend
# ---------------------------------------------------------------------------

class OllamaBackend(CaptionBackend):
    """Caption via a locally running Ollama server (e.g. llava, bakllava, moondream)."""

    def __init__(self, model: str = "llava", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def generate(
        self,
        image_path: Path,
        tags: Optional[List[str]] = None,
        prompt: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        try:
            import requests
        except ImportError:
            logger.error("OllamaBackend requires the 'requests' package: pip install requests")
            return ""
        try:
            b64 = self._encode_image_b64(image_path)
            user_text = self._build_user_text(tags, prompt)
            payload: dict = {
                "model": self.model,
                "prompt": user_text,
                "images": [b64],
                "stream": False,
            }
            if system_prompt:
                payload["system"] = system_prompt
            resp = requests.post(
                f"{self.base_url}/api/generate", json=payload, timeout=120
            )
            resp.raise_for_status()
            data = resp.json()
            return (data.get("response") or "").strip()
        except Exception as exc:
            logger.error("OllamaBackend.generate failed: %s", exc)
            return ""

    @classmethod
    def list_models(cls, base_url: str = "http://localhost:11434") -> List[str]:
        """Return names of vision-capable models available in the Ollama server."""
        try:
            import requests
            resp = requests.get(f"{base_url.rstrip('/')}/api/tags", timeout=10)
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            return models
        except Exception:
            return []


# ---------------------------------------------------------------------------
# OpenAI backend
# ---------------------------------------------------------------------------

class OpenAIBackend(CaptionBackend):
    """Caption via OpenAI API (GPT-4o, GPT-4 Vision, etc.)."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.api_key = api_key
        self.model = model

    def generate(
        self,
        image_path: Path,
        tags: Optional[List[str]] = None,
        prompt: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        try:
            from openai import OpenAI
        except ImportError:
            logger.error("OpenAIBackend requires the 'openai' package: pip install openai")
            return ""
        try:
            client = OpenAI(api_key=self.api_key)
            b64 = self._encode_image_b64(image_path)
            user_text = self._build_user_text(tags, prompt)
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            })
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=512,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:
            logger.error("OpenAIBackend.generate failed: %s", exc)
            return ""


# ---------------------------------------------------------------------------
# Anthropic backend
# ---------------------------------------------------------------------------

class AnthropicBackend(CaptionBackend):
    """Caption via Anthropic Claude API (claude-3-5-sonnet, claude-3-haiku, etc.)."""

    def __init__(self, api_key: str, model: str = "claude-3-5-haiku-20241022"):
        self.api_key = api_key
        self.model = model

    def generate(
        self,
        image_path: Path,
        tags: Optional[List[str]] = None,
        prompt: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        try:
            import anthropic
        except ImportError:
            logger.error("AnthropicBackend requires the 'anthropic' package: pip install anthropic")
            return ""
        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            b64 = self._encode_image_b64(image_path)
            user_text = self._build_user_text(tags, prompt)
            kwargs: dict = {
                "model": self.model,
                "max_tokens": 512,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": b64,
                                },
                            },
                            {"type": "text", "text": user_text},
                        ],
                    }
                ],
            }
            if system_prompt:
                kwargs["system"] = system_prompt
            message = client.messages.create(**kwargs)
            return (message.content[0].text or "").strip()
        except Exception as exc:
            logger.error("AnthropicBackend.generate failed: %s", exc)
            return ""


# ---------------------------------------------------------------------------
# Google Gemini backend
# ---------------------------------------------------------------------------

class GeminiBackend(CaptionBackend):
    """Caption via Google Gemini API (gemini-1.5-flash, gemini-2.0-flash, etc.).

    Uses the ``google-genai`` SDK (``pip install google-genai``).
    The older ``google-generativeai`` package is no longer compatible.
    """

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self.api_key = api_key
        self.model = model

    def generate(
        self,
        image_path: Path,
        tags: Optional[List[str]] = None,
        prompt: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError:
            logger.error(
                "GeminiBackend requires the 'google-genai' package: "
                "pip install google-genai"
            )
            return ""
        try:
            import io
            client = genai.Client(api_key=self.api_key)
            img = Image.open(image_path).convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            img_bytes = buf.getvalue()
            user_text = self._build_user_text(tags, prompt)
            contents: list = [
                genai_types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                user_text,
            ]
            config_kwargs: dict = {}
            if system_prompt:
                config_kwargs["system_instruction"] = system_prompt
            cfg = genai_types.GenerateContentConfig(**config_kwargs) if config_kwargs else None
            response = client.models.generate_content(
                model=self.model,
                contents=contents,
                config=cfg,
            )
            return (response.text or "").strip()
        except Exception as exc:
            logger.error("GeminiBackend.generate failed: %s", exc)
            return ""


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_caption_backend(profile: Optional[dict] = None) -> CaptionBackend:
    """Return the appropriate :class:`CaptionBackend` for the given profile dict.

    Falls back to ``LocalModelBackend("joycaption")`` if profile is ``None``
    or the source is unrecognised.

    Profile keys used
    -----------------
    caption_source : str
        One of ``"local"``, ``"ollama"``, ``"openai"``, ``"anthropic"``, ``"gemini"``.
    caption_local_model : str
        Used when *caption_source* is ``"local"``.  One of ``"joycaption"``,
        ``"florence2"``, ``"gemma3"``.
    ollama_url : str
    ollama_model : str
    openai_api_key : str
    openai_model : str
    anthropic_api_key : str
    anthropic_model : str
    gemini_api_key : str
    gemini_model : str
    """
    p = profile or {}
    source = (p.get("caption_source") or "local").lower()

    if source == "ollama":
        return OllamaBackend(
            model=p.get("ollama_model") or "llava",
            base_url=p.get("ollama_url") or "http://localhost:11434",
        )
    if source == "openai":
        return OpenAIBackend(
            api_key=p.get("openai_api_key") or "",
            model=p.get("openai_model") or "gpt-4o",
        )
    if source == "anthropic":
        return AnthropicBackend(
            api_key=p.get("anthropic_api_key") or "",
            model=p.get("anthropic_model") or "claude-3-5-haiku-20241022",
        )
    if source == "gemini":
        return GeminiBackend(
            api_key=p.get("gemini_api_key") or "",
            model=p.get("gemini_model") or "gemini-2.0-flash",
        )

    # Default: local transformers model
    return LocalModelBackend(model_name=p.get("caption_local_model") or "joycaption")
