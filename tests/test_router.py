from __future__ import annotations

from pathlib import Path

from app.feishu.router_helpers import (
    classify_intent,
    index_image_path,
    resolve_indexed_image,
)


class TestClassifyIntent:
    def test_shensi_analyze_exact(self) -> None:
        assert classify_intent("慎思分析") == "shensi_analyze"

    def test_shensi_analyze_with_extra_text(self) -> None:
        assert classify_intent("请慎思分析一下") == "shensi_analyze"

    def test_confirm_exact(self) -> None:
        assert classify_intent("确认入库") == "confirm"

    def test_confirm_short(self) -> None:
        assert classify_intent("确认") == "confirm"

    def test_discard_exact(self) -> None:
        assert classify_intent("丢弃") == "discard"

    def test_help_exact(self) -> None:
        assert classify_intent("帮助") == "help"

    def test_unknown_random(self) -> None:
        assert classify_intent("今天天气不错") == "unknown"

    def test_unknown_empty(self) -> None:
        assert classify_intent("") == "unknown"
        assert classify_intent("   ") == "unknown"

    def test_correction_is_unknown(self) -> None:
        assert classify_intent("第三题其实是对的") == "unknown"


class TestIndexImagePath:
    def test_generates_expected_structure(self, tmp_path: Path) -> None:
        got = index_image_path(
            "oc_test_chat", "ou_test_user", index_dir=tmp_path
        )
        expected_dir = tmp_path / "oc_test_chat"
        expected = expected_dir / "ou_test_user.path"
        assert got == expected

    def test_sanitises_special_chars(self, tmp_path: Path) -> None:
        got = index_image_path(
            "oc:chat@123", "user/<>", index_dir=tmp_path
        )
        # ':' '@' '/' '<' '>' all become '_'
        assert ":" not in str(got.parent.name)
        assert "@" not in str(got.parent.name)
        assert got.name.endswith(".path")

    def test_default_index_dir(self) -> None:
        got = index_image_path("chat", "user")
        assert ".hermes" in str(got) or "shensi_image_index" in str(got)


class TestResolveIndexedImage:
    def test_returns_none_when_index_missing(self, tmp_path: Path) -> None:
        assert resolve_indexed_image("chat", "user", index_dir=tmp_path) is None

    def test_returns_none_when_indexed_image_deleted(self, tmp_path: Path) -> None:
        index_target = index_image_path("chat", "user", index_dir=tmp_path)
        index_target.parent.mkdir(parents=True, exist_ok=True)
        index_target.write_text("/nonexistent/img.jpg")
        assert resolve_indexed_image("chat", "user", index_dir=tmp_path) is None

    def test_returns_path_when_indexed_image_exists(self, tmp_path: Path) -> None:
        img = tmp_path / "real.jpg"
        img.write_text("fake jpeg")

        index_target = index_image_path("chat", "user", index_dir=tmp_path)
        index_target.parent.mkdir(parents=True, exist_ok=True)
        index_target.write_text(str(img))

        got = resolve_indexed_image("chat", "user", index_dir=tmp_path)
        assert got == img

    def test_no_global_cache_fallback(self, tmp_path: Path) -> None:
        """Even with images in a sibling dir, non-indexed chat returns None."""
        other_img = tmp_path / "other.jpg"
        other_img.write_text("other")
        # Write an index for a different chat
        other_index = index_image_path("other_chat", "user", index_dir=tmp_path)
        other_index.parent.mkdir(parents=True, exist_ok=True)
        other_index.write_text(str(other_img))

        # Our chat has no index → None (no fallback to other_chat's image)
        assert resolve_indexed_image("our_chat", "user", index_dir=tmp_path) is None
