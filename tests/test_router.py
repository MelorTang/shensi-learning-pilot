from __future__ import annotations

from pathlib import Path

from app.feishu.router_helpers import (
    classify_intent,
    has_mention,
    index_image_path,
    resolve_indexed_image,
    strip_mention,
)


class TestHasMention:
    def test_with_mention(self) -> None:
        assert has_mention("@机器人 帮助") is True

    def test_without_mention(self) -> None:
        assert has_mention("帮助") is False
        assert has_mention("慎思分析") is False

    def test_empty(self) -> None:
        assert has_mention("") is False


class TestStripMention:
    def test_removes_at_mention_prefix(self) -> None:
        assert strip_mention("@慎思错题机器人 帮助") == "帮助"

    def test_removes_at_user_id(self) -> None:
        assert strip_mention("@_user_1 确认入库") == "确认入库"

    def test_no_mention_unchanged(self) -> None:
        assert strip_mention("帮助") == "帮助"
        assert strip_mention("慎思分析") == "慎思分析"

    def test_multiple_mentions(self) -> None:
        assert strip_mention("@bot1 @bot2 丢弃") == "丢弃"

    def test_only_mention(self) -> None:
        assert strip_mention("@机器人") == ""

    def test_intent_with_mention(self) -> None:
        assert classify_intent(strip_mention("@慎思错题机器人 帮助")) == "help"
        assert classify_intent(strip_mention("@_user_1 慎思分析")) == "shensi_analyze"
        assert classify_intent(strip_mention("@bot 确认入库")) == "confirm"
        assert classify_intent(strip_mention("@bot 日报")) == "unknown"


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

    # daily report / review tasks moved to tutor bot → router returns unknown
    def test_daily_report_is_unknown(self) -> None:
        assert classify_intent("今日日报") == "unknown"
        assert classify_intent("日报") == "unknown"
        assert classify_intent("今日总结") == "unknown"

    def test_review_tasks_is_unknown(self) -> None:
        assert classify_intent("复习任务") == "unknown"
        assert classify_intent("今日复习") == "unknown"
        assert classify_intent("待复习") == "unknown"


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
