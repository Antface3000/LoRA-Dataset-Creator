"""Built-in caption system-prompt presets and helpers for the saved prompt library."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.config import CAPTION_SYSTEM_PROMPT

# Stable ids for built-ins (not shown in menu; use menu_label for UI)
BUILTIN_PRESETS: List[Dict[str, str]] = [
    {
        "id": "general",
        "menu_label": "General descriptive",
        "system": (
            "You write clear, neutral image captions for a general audience. "
            "Output 1–3 sentences of natural prose describing the scene, subject, and style. "
            "Do not begin with preambles (no 'Here is…', 'Certainly!', etc.). "
            "Output only the caption. "
            "If tags or keywords are provided, use them as hints only—you may summarize or omit minor details; "
            "do not force explicit or anatomical wording unless it is essential to the image. "
            "Do not output comma-separated tag lists or lines starting with 'Tags:'."
        ),
        "user": "",
    },
    {
        "id": "lora",
        "menu_label": "LoRA / full tag fidelity",
        "system": CAPTION_SYSTEM_PROMPT,
        "user": "",
    },
    {
        "id": "short",
        "menu_label": "Short / one sentence",
        "system": (
            "You caption images in a single concise sentence. "
            "No preamble or acknowledgement—output only that sentence. "
            "Do not output tag lists."
        ),
        "user": "",
    },
]

SAVED_PREFIX = "Saved: "


def menu_label_for_saved(name: str) -> str:
    return f"{SAVED_PREFIX}{name}"


def is_saved_menu_label(value: str) -> bool:
    return bool(value) and value.startswith(SAVED_PREFIX)


def saved_name_from_menu_label(value: str) -> str:
    return value[len(SAVED_PREFIX) :].strip() if is_saved_menu_label(value) else ""


def builtin_by_menu_label(menu_label: str) -> Optional[Dict[str, str]]:
    for p in BUILTIN_PRESETS:
        if p["menu_label"] == menu_label:
            return p
    return None


def build_menu_values(library: List[Dict[str, Any]]) -> List[str]:
    values = [p["menu_label"] for p in BUILTIN_PRESETS]
    for item in library:
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            values.append(menu_label_for_saved(name.strip()))
    return values


def resolve_selection(menu_value: str, library: List[Dict[str, Any]]) -> Optional[Tuple[str, str]]:
    """Return (system, user) for the chosen menu row, or None."""
    b = builtin_by_menu_label(menu_value)
    if b is not None:
        return (b["system"], b.get("user") or "")
    if is_saved_menu_label(menu_value):
        want = saved_name_from_menu_label(menu_value)
        for item in library:
            if item.get("name") == want:
                sys_t = item.get("system") if isinstance(item.get("system"), str) else ""
                usr = item.get("user") if isinstance(item.get("user"), str) else ""
                return (sys_t, usr)
    return None


def normalize_library_item(raw: Any) -> Optional[Dict[str, str]]:
    if not isinstance(raw, dict):
        return None
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    system = raw.get("system") if isinstance(raw.get("system"), str) else ""
    user = raw.get("user") if isinstance(raw.get("user"), str) else ""
    return {"name": name.strip(), "system": system, "user": user}


def unique_saved_name(library: List[Dict[str, Any]], base: str) -> str:
    names = {item["name"] for item in library if isinstance(item.get("name"), str)}
    if base not in names:
        return base
    n = 2
    while f"{base} ({n})" in names:
        n += 1
    return f"{base} ({n})"
