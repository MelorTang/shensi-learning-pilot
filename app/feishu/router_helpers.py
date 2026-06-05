"""Pure helpers for the Shensi direct Feishu message router.

These are kept separate from scripts/run_feishu_ws.py so they can be
imported and tested without pulling in lark_oapi or FeishuClient.
"""

from __future__ import annotations

from pathlib import Path
import os
import re


# ---------------------------------------------------------------------------
# Intent classifier
# ---------------------------------------------------------------------------

def classify_intent(text: str) -> str:
    """Classify a user text message into a router intent.

    Returns one of:
      'shensi_analyze' — user wants analysis
      'confirm'        — user wants to confirm the latest pending result
      'discard'        — user wants to discard the latest pending result
      'help'           — user wants help
      'unknown'        — no recognised intent
    """
    cleaned = text.strip()
    if not cleaned:
        return "unknown"

    if "慎思分析" in cleaned or "提交这张错题" in cleaned or "分析刚才" in cleaned:
        return "shensi_analyze"

    if cleaned == "帮助" or cleaned.startswith("帮助"):
        return "help"

    # Exact or near-exact confirm / discard
    if cleaned in ("确认入库", "确认") or "确认入库" in cleaned:
        return "confirm"
    if cleaned in ("丢弃", "不要") or "丢弃" in cleaned:
        return "discard"

    return "unknown"


# ---------------------------------------------------------------------------
# Index path helper (mirrors shensi-index-image logic)
# ---------------------------------------------------------------------------

def _safe_key(value: str) -> str:
    """Replace characters unsafe for filenames with '_'."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)


def index_image_path(
    chat_id: str,
    sender_id: str,
    *,
    index_dir: str | Path | None = None,
) -> Path:
    """Return the path where the image index file should be written.

    Mirrors the logic of ``scripts/cloud/shensi-index-image``:
      <index_dir>/<safe_chat>/<safe_sender>.path
    """
    base = Path(index_dir) if index_dir else Path(
        os.path.expanduser("~/.hermes/shensi_image_index")
    )
    safe_chat = _safe_key(chat_id)
    safe_sender = _safe_key(sender_id)
    return base / safe_chat / f"{safe_sender}.path"


def resolve_indexed_image(
    chat_id: str,
    sender_id: str,
    *,
    index_dir: str | Path | None = None,
) -> Path | None:
    """Look up the chat+sender index and return the cached image path.

    Returns None when the index file is missing or the referenced image
    no longer exists.  Does NOT fall back to a global cache.
    """
    target = index_image_path(chat_id, sender_id, index_dir=index_dir)
    if not target.exists():
        return None
    raw = target.read_text().strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.exists() else None
