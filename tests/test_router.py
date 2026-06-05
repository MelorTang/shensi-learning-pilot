from __future__ import annotations

from pathlib import Path
import tempfile

from app.feishu.router_helpers import classify_intent, index_image_path


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
