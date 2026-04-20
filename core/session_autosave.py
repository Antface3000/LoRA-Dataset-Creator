"""Persist wizard session (tags, captions, image list) to disk for restore after restart."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.config import VALID_EXTENSIONS
from core.session import Session, SessionItem, get_session

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
AUTOSAVE_FILENAME = "wizard_session_autosave.json"


def autosave_path() -> Path:
    """Same directory as project-root config (flux_prep_config.json)."""
    return Path(__file__).resolve().parent.parent / AUTOSAVE_FILENAME


def _path_opt(s: Optional[str]) -> Optional[Path]:
    if not s:
        return None
    return Path(s)


def session_to_dict(
    session: Session,
    *,
    caption_selected_index: Optional[int] = None,
    active_main_tab: Optional[str] = None,
) -> Dict[str, Any]:
    items_out: List[Dict[str, Any]] = []
    for it in session.items:
        cb = it.crop_box
        items_out.append(
            {
                "original_path": str(it.original_path.resolve()),
                "tags": list(it.tags),
                "tags_from_scan": list(it.tags_from_scan),
                "caption": it.caption or "",
                "output_stem": it.output_stem,
                "crop_box": list(cb) if cb is not None else None,
                "bucket": it.bucket or "square",
            }
        )
    out: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_folder": str(session.source_folder.resolve())
        if session.source_folder
        else None,
        "output_folder": str(session.output_folder.resolve())
        if session.output_folder
        else None,
        "processed_folder": str(session.processed_folder.resolve())
        if session.processed_folder
        else None,
        "output_format": session.get_output_format(),
        "caption_selected_index": caption_selected_index,
        "items": items_out,
    }
    if active_main_tab:
        out["active_main_tab"] = active_main_tab
    return out


def apply_session_dict(
    session: Session, data: Dict[str, Any]
) -> Tuple[int, int]:
    """Restore session from snapshot. Skips missing / invalid image paths.

    Returns:
        (skipped_count, restored_item_count)
    """
    ver = data.get("schema_version", 0)
    if ver != SCHEMA_VERSION:
        logger.warning("Session autosave schema %s != %s; attempting load anyway", ver, SCHEMA_VERSION)

    session.source_folder = _path_opt(data.get("source_folder"))
    session.output_folder = _path_opt(data.get("output_folder"))
    pf = data.get("processed_folder")
    session.processed_folder = _path_opt(pf) if pf else session.processed_folder

    fmt = data.get("output_format")
    if fmt in ("Tags only", "Natural language", "Both"):
        session.set_output_format(fmt)

    new_items: List[SessionItem] = []
    skipped = 0
    for raw in data.get("items") or []:
        p_str = raw.get("original_path")
        if not p_str:
            skipped += 1
            continue
        p = Path(p_str)
        if not p.is_file() or p.suffix.lower() not in VALID_EXTENSIONS:
            skipped += 1
            continue
        p = p.resolve()
        cb = raw.get("crop_box")
        crop_box: Optional[Tuple[int, int, int, int]] = None
        if cb is not None and isinstance(cb, (list, tuple)) and len(cb) == 4:
            try:
                crop_box = (int(cb[0]), int(cb[1]), int(cb[2]), int(cb[3]))
            except (TypeError, ValueError):
                crop_box = None
        item = SessionItem(
            original_path=p,
            tags=list(raw.get("tags") or []),
            tags_from_scan=list(raw.get("tags_from_scan") or []),
            caption=str(raw.get("caption") or ""),
            output_stem=raw.get("output_stem") or None,
            crop_box=crop_box,
            bucket=str(raw.get("bucket") or "square"),
        )
        new_items.append(item)

    session.replace_items(new_items)
    return skipped, len(new_items)


def save_session_snapshot(
    session: Optional[Session] = None,
    *,
    caption_selected_index: Optional[int] = None,
    active_main_tab: Optional[str] = None,
) -> None:
    session = session or get_session()
    path = autosave_path()
    payload = session_to_dict(
        session,
        caption_selected_index=caption_selected_index,
        active_main_tab=active_main_tab,
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
    except Exception:
        logger.exception("Failed to write session autosave to %s", path)


def load_session_snapshot() -> Optional[Dict[str, Any]]:
    path = autosave_path()
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to read session autosave from %s", path)
        return None


def delete_autosave_file() -> None:
    path = autosave_path()
    try:
        if path.is_file():
            path.unlink()
    except Exception:
        logger.exception("Failed to delete session autosave %s", path)
