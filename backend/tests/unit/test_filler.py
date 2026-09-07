"""Tests for chaoxing.solvers.quiz.filler — answer filling and question type detection."""
import json
from unittest.mock import patch, MagicMock

import pytest

from chaoxing.solvers.quiz.filler import (
    _is_unanswerable,
    _judge_answer_variants,
    _detect_question_types,
    _fill_answers,
    _click_option,
    _click_option_dom,
    _fill_blank,
    UNANSWERABLE_MARKERS,
)


# ── _is_unanswerable ─────────────────────────────────────────────

class TestIsUnanswerable:
    """Tests for _is_unanswerable — detecting AI-unanswerable markers."""

    def test_none_answer_is_unanswerable(self):
        """None answer should be treated as unanswerable."""
        assert _is_unanswerable(None) is True

    def test_empty_string_is_unanswerable(self):
        """Empty string should be treated as unanswerable."""
        assert _is_unanswerable("") is True

    def test_empty_list_is_unanswerable(self):
        """Empty list should be treated as unanswerable."""
        assert _is_unanswerable([]) is True

    def test_known_marker_wufapanduan(self):
        """Answer containing '无法判断' should be flagged."""
        assert _is_unanswerable("无法判断") is True

    def test_known_marker_wufaqueding(self):
        """Answer containing '无法确定' should be flagged."""
        assert _is_unanswerable("无法确定") is True

    def test_known_marker_xinxibuzu(self):
        """Answer containing '信息不足' should be flagged."""
        assert _is_unanswerable("信息不足") is True

    def test_known_marker_unanswerable(self):
        """Answer containing 'unanswerable' should be flagged."""
        assert _is_unanswerable("unanswerable") is True

    def test_known_marker_cannot_determine(self):
        """Answer containing 'cannot determine' should be flagged."""
        assert _is_unanswerable("cannot determine") is True

    def test_known_marker_not_enough_info(self):
        """Answer containing 'not enough info' should be flagged."""
        assert _is_unanswerable("not enough info") is True

    def test_normal_answer_not_unanswerable(self):
        """Normal answer like 'A' should NOT be flagged."""
        assert _is_unanswerable("A") is False

    def test_long_answer_not_unanswerable(self):
        """Long descriptive answer should NOT be flagged."""
        assert _is_unanswerable("贝叶斯定理的应用") is False

    def test_substring_false_positive_case(self):
        """Answer containing marker as sub-clause should NOT be flagged.

        Example: 'The answer can be determined from the data. There is
        not enough info about option C specifically.' — this is NOT an
        unanswerable question, just a comment about option C.
        """
        answer = (
            "The answer can be determined from the given data. "
            "There is not enough info about option C specifically, "
            "but the correct answer is B."
        )
        assert _is_unanswerable(answer) is False, (
            "Substring containing 'not enough info' in context should "
            "NOT trigger unanswerable — only prefix/exact match should"
        )

    def test_marker_as_prefix_is_flagged(self):
        """Answer STARTING with a marker should be flagged."""
        assert _is_unanswerable("无法判断，题目信息不完整") is True

    def test_case_insensitive_match(self):
        """Markers should be matched case-insensitively."""
        assert _is_unanswerable("CANNOT DETERMINE") is True
        assert _is_unanswerable("Cannot Determine") is True

    def test_whitespace_insensitive_match(self):
        """Leading/trailing whitespace should not affect matching."""
        assert _is_unanswerable("  无法判断  ") is True

    def test_list_answer_with_valid_content(self):
        """List answer like ['A', 'B'] should NOT be flagged."""
        assert _is_unanswerable(["A", "B"]) is False

    def test_custom_answer_types(self):
        """Answer as a dict with 'answer' key should be checked properly."""
        # _is_unanswerable receives the answer value directly
        assert _is_unanswerable({"answer": "A"}) is False


# ── _judge_answer_variants ───────────────────────────────────────

class TestJudgeAnswerVariants:
    """Tests for _judge_answer_variants — judge surface-form expansion."""

    def test_true_form_expands_to_true_polarity_only(self):
        """'对' should expand to all true forms, never a false form."""
        out = _judge_answer_variants("对")
        assert out[0] == "对"  # original first
        assert "正确" in out and "√" in out and "A" in out
        # polarity never crossed
        assert "错" not in out and "错误" not in out and "B" not in out

    def test_false_form_expands_to_false_polarity_only(self):
        """'错误' should expand to all false forms, never a true form."""
        out = _judge_answer_variants("错误")
        assert out[0] == "错误"  # original first
        assert "错" in out and "×" in out and "B" in out
        assert "对" not in out and "正确" not in out and "A" not in out

    def test_letter_A_is_true_polarity(self):
        """'A' is the canonical true option label -> true forms."""
        out = _judge_answer_variants("A")
        assert out[0] == "A"
        assert "对" in out and "正确" in out
        assert "B" not in out and "错" not in out

    def test_letter_B_is_false_polarity(self):
        """'B' is the canonical false option label -> false forms."""
        out = _judge_answer_variants("B")
        assert out[0] == "B"
        assert "错" in out and "错误" in out
        assert "A" not in out and "对" not in out

    def test_original_always_first(self):
        """The original surface form must be tried before any variant."""
        assert _judge_answer_variants("正确")[0] == "正确"
        assert _judge_answer_variants("√")[0] == "√"

    def test_no_duplicates(self):
        """Expansion must not contain duplicates."""
        out = _judge_answer_variants("对")
        assert len(out) == len(set(out))

    def test_case_insensitive_token(self):
        """'true'/'TRUE' are not in our form set; only explicit forms expand.

        Guards against accidental over-expansion: a non-judge token returns
        unchanged.
        """
        # 'a' lowercased matches 'A' form -> expands
        assert len(_judge_answer_variants("a")) > 1

    def test_non_judge_string_untouched(self):
        """A fill/essay answer must be returned unchanged (single element)."""
        assert _judge_answer_variants("0.5") == ["0.5"]
        assert _judge_answer_variants("The derivative is positive") == \
            ["The derivative is positive"]

    def test_non_str_untouched(self):
        """Non-str answers returned as single-element list, untouched."""
        assert _judge_answer_variants(["A", "B"]) == [["A", "B"]]
        assert _judge_answer_variants(None) == [None]


# ── _detect_question_types ──────────────────────────────────────
# This function uses pw_run_code_file which requires a real browser.
# We mock the browser layer to test the parsing logic.

MOCK_QTYPE_JSON = json.dumps({
    "ok": True,
    "types": [
        {"index": 1, "type": "single", "optionCount": 4, "hasTextarea": False,
         "hasCheckbox": False, "hasRadio": True},
        {"index": 2, "type": "multi", "optionCount": 4, "hasTextarea": False,
         "hasCheckbox": True, "hasRadio": False},
        {"index": 3, "type": "judge", "optionCount": 2, "hasTextarea": False,
         "hasCheckbox": False, "hasRadio": True},
        {"index": 4, "type": "fill", "optionCount": 1, "hasTextarea": True,
         "hasCheckbox": False, "hasRadio": False},
        {"index": 5, "type": "essay", "optionCount": 0, "hasTextarea": True,
         "hasCheckbox": False, "hasRadio": False},
    ],
    "containerCount": 5,
})


class TestDetectQuestionTypes:
    """Tests for _detect_question_types with mocked browser."""

    @patch("chaoxing.solvers.quiz.filler.pw_run_code_file")
    @patch("chaoxing.solvers.quiz.filler.pw_extract_result")
    def test_detects_single_multi_judge_fill_essay(
        self, mock_extract, mock_run
    ):
        """Should correctly identify all 5 question types."""
        mock_extract.return_value = MOCK_QTYPE_JSON
        mock_run.return_value = "ok"

        result = _detect_question_types()

        assert isinstance(result, list)
        assert len(result) == 5
        types = {t["index"]: t["type"] for t in result}
        assert types[1] == "single"
        assert types[2] == "multi"
        assert types[3] == "judge"
        assert types[4] == "fill"
        assert types[5] == "essay"

    @patch("chaoxing.solvers.quiz.filler.pw_run_code_file")
    @patch("chaoxing.solvers.quiz.filler.pw_extract_result")
    def test_no_iframe_returns_empty_list(self, mock_extract, mock_run):
        """Should return empty list when no iframe is found."""
        mock_extract.return_value = json.dumps({
            "ok": False, "reason": "no-iframe"
        })
        mock_run.return_value = "ok"

        result = _detect_question_types()
        assert result == []

    @patch("chaoxing.solvers.quiz.filler.pw_run_code_file")
    @patch("chaoxing.solvers.quiz.filler.pw_extract_result")
    def test_invalid_json_returns_empty_list(self, mock_extract, mock_run):
        """Should return empty list when JSON parsing fails."""
        mock_extract.return_value = "not valid json {{{"
        mock_run.return_value = "ok"

        result = _detect_question_types()
        assert result == []

    @patch("chaoxing.solvers.quiz.filler.pw_run_code_file")
    @patch("chaoxing.solvers.quiz.filler.pw_extract_result")
    def test_empty_types_returns_empty_list(self, mock_extract, mock_run):
        """Should handle empty types array."""
        mock_extract.return_value = json.dumps({
            "ok": True, "types": [], "containerCount": 0
        })
        mock_run.return_value = "ok"

        result = _detect_question_types()
        assert result == []

    @patch("chaoxing.solvers.quiz.filler.pw_run_code_file")
    @patch("chaoxing.solvers.quiz.filler.pw_extract_result")
    def test_no_containers_returns_empty(self, mock_extract, mock_run):
        """Should return empty list when no containers found."""
        mock_extract.return_value = json.dumps({
            "ok": False, "reason": "no-containers"
        })
        mock_run.return_value = "ok"

        result = _detect_question_types()
        assert result == []

    @patch("chaoxing.solvers.quiz.filler.pw_run_code_file")
    @patch("chaoxing.solvers.quiz.filler.pw_extract_result")
    def test_answertype_anchor_mixed_single_multi(self, mock_extract, mock_run):
        """Regression for the all-multi bug (account-0 概率论 1.6).

        Real DOM dump (2026-06-27): every .TiMu had radio=0, checkbox=0,
        before-after=4 (== real option count, NOT over-counted). With no
        form inputs and optionCount=4, the OLD heuristic sent every question
        to the `optionCount >= 4 -> multi` fallback, misclassifying all 27
        single-choice questions as multi. The fix reads the authoritative
        input[id^=answertype] value (0=single, 1=multi). This payload mirrors
        the real 1.6 shape: 27 singles (answerType "0") + 3 multis ("1").

        The JS layer already maps answerType->type (the browser-side code we
        can't unit-test), so the emitted `type` here reflects that mapping;
        this test pins the contract that the parser surfaces a single/multi
        MIX rather than the all-multi regression.
        """
        types = []
        for i in range(1, 31):
            at = "0" if i <= 27 else "1"
            types.append({
                "index": i,
                "type": "single" if at == "0" else "multi",
                "optionCount": 4,        # before-after == real options
                "hasTextarea": False,
                "hasCheckbox": False,    # styled <li>, no form inputs
                "hasRadio": False,
                "answerType": at,
            })
        mock_extract.return_value = json.dumps({
            "ok": True, "types": types, "containerCount": 30,
        })
        mock_run.return_value = "ok"

        result = _detect_question_types()
        assert len(result) == 30
        type_counts = {}
        for t in result:
            type_counts[t["type"]] = type_counts.get(t["type"], 0) + 1
        # The regression was {'multi': 30}; correct is a single/multi mix.
        assert type_counts == {"single": 27, "multi": 3}, (
            f"Expected 27 single + 3 multi (per answertype field), got "
            f"{type_counts} — the all-multi regression must not return"
        )
        # Spot-check boundary: q27 single, q28 multi.
        by_idx = {t["index"]: t["type"] for t in result}
        assert by_idx[27] == "single"
        assert by_idx[28] == "multi"


# ── _fill_answers ────────────────────────────────────────────────

class TestFillAnswers:
    """Tests for _fill_answers answer dispatch."""

    @patch("chaoxing.solvers.quiz.filler._detect_question_types")
    @patch("chaoxing.solvers.quiz.filler._fill_blank")
    @patch("chaoxing.solvers.quiz.filler._click_option")
    def test_fills_single_choice_answers(
        self, mock_click, mock_fill_blank, mock_detect
    ):
        """Should dispatch single-choice answers to _click_option."""
        mock_detect.return_value = [
            {"index": 1, "type": "single", "optionCount": 4,
             "hasTextarea": False, "hasCheckbox": False, "hasRadio": True},
            {"index": 2, "type": "single", "optionCount": 4,
             "hasTextarea": False, "hasCheckbox": False, "hasRadio": True},
        ]

        answers = [
            {"index": 1, "answer": "A"},
            {"index": 2, "answer": "B"},
        ]

        result = _fill_answers(answers)
        assert result == 2
        assert mock_click.call_count == 2

    @patch("chaoxing.solvers.quiz.filler._detect_question_types")
    @patch("chaoxing.solvers.quiz.filler._fill_blank")
    @patch("chaoxing.solvers.quiz.filler._click_option")
    def test_fills_multi_select_answers(
        self, mock_click, mock_fill_blank, mock_detect
    ):
        """Should click each option in multi-select answers."""
        mock_detect.return_value = [
            {"index": 1, "type": "multi", "optionCount": 4,
             "hasTextarea": False, "hasCheckbox": True, "hasRadio": False},
        ]

        answers = [
            {"index": 1, "answer": ["A", "B", "D"]},
        ]

        result = _fill_answers(answers)
        assert result == 1
        assert mock_click.call_count == 3  # One click per option

    @patch("chaoxing.solvers.quiz.filler._detect_question_types")
    @patch("chaoxing.solvers.quiz.filler._fill_blank")
    @patch("chaoxing.solvers.quiz.filler._click_option")
    def test_fills_blank_questions(
        self, mock_click, mock_fill_blank, mock_detect
    ):
        """Should dispatch fill-in-the-blank questions to _fill_blank."""
        mock_detect.return_value = [
            {"index": 1, "type": "fill", "optionCount": 1,
             "hasTextarea": True, "hasCheckbox": False, "hasRadio": False},
        ]
        mock_fill_blank.return_value = True

        answers = [
            {"index": 1, "answer": "0.5"},
        ]

        result = _fill_answers(answers)
        assert result == 1
        mock_fill_blank.assert_called_once()

    @patch("chaoxing.solvers.quiz.filler._detect_question_types")
    @patch("chaoxing.solvers.quiz.filler._fill_blank")
    @patch("chaoxing.solvers.quiz.filler._click_option")
    def test_skips_unanswerable_questions(
        self, mock_click, mock_fill_blank, mock_detect
    ):
        """Should skip questions marked as unanswerable."""
        mock_detect.return_value = [
            {"index": 1, "type": "single", "optionCount": 4,
             "hasTextarea": False, "hasCheckbox": False, "hasRadio": True},
            {"index": 2, "type": "single", "optionCount": 4,
             "hasTextarea": False, "hasCheckbox": False, "hasRadio": True},
        ]

        answers = [
            {"index": 1, "answer": "A"},
            {"index": 2, "answer": "无法判断"},
        ]

        result = _fill_answers(answers)
        assert result == 1  # Only Q1 filled
        mock_click.assert_called_once()

    @patch("chaoxing.solvers.quiz.filler._detect_question_types")
    @patch("chaoxing.solvers.quiz.filler._fill_blank")
    @patch("chaoxing.solvers.quiz.filler._click_option")
    def test_empty_answers_returns_zero(
        self, mock_click, mock_fill_blank, mock_detect
    ):
        """Should return 0 when answers list is empty."""
        result = _fill_answers([])
        assert result == 0
        mock_click.assert_not_called()

    @patch("chaoxing.solvers.quiz.filler._detect_question_types")
    @patch("chaoxing.solvers.quiz.filler._fill_blank")
    @patch("chaoxing.solvers.quiz.filler._click_option")
    def test_no_type_map_falls_back_to_click(
        self, mock_click, mock_fill_blank, mock_detect
    ):
        """Should fall back to _click_option when type detection fails."""
        mock_detect.return_value = []  # No types detected

        answers = [
            {"index": 1, "answer": "C"},
        ]

        result = _fill_answers(answers)
        assert result == 1
        mock_click.assert_called_once()

    @patch("chaoxing.solvers.quiz.filler._detect_question_types")
    @patch("chaoxing.solvers.quiz.filler._fill_blank")
    @patch("chaoxing.solvers.quiz.filler._click_option")
    def test_fill_blank_fallback_to_click(
        self, mock_click, mock_fill_blank, mock_detect
    ):
        """Should fall back to _click_option when _fill_blank fails."""
        mock_detect.return_value = [
            {"index": 1, "type": "fill", "optionCount": 1,
             "hasTextarea": True, "hasCheckbox": False, "hasRadio": False},
        ]
        mock_fill_blank.return_value = False  # Fill blank fails

        answers = [
            {"index": 1, "answer": "0.5"},
        ]

        result = _fill_answers(answers)
        assert result == 1
        mock_fill_blank.assert_called_once()
        mock_click.assert_called_once()  # Fallback called

    @patch("chaoxing.solvers.quiz.filler._detect_question_types")
    @patch("chaoxing.solvers.quiz.filler._fill_blank")
    @patch("chaoxing.solvers.quiz.filler._click_option")
    def test_judge_tries_variants_until_success(
        self, mock_click, mock_fill_blank, mock_detect
    ):
        """Judge dispatch should try same-polarity variants until one clicks,
        then STOP (never select two options)."""
        mock_detect.return_value = [
            {"index": 1, "type": "judge", "optionCount": 2,
             "hasTextarea": False, "hasCheckbox": False, "hasRadio": True},
        ]
        # AI returned "对"; option renders as "正确". First call ("对") misses,
        # second ("正确") hits -> should stop there.
        mock_click.side_effect = [False, True]

        answers = [{"index": 1, "answer": "对"}]
        result = _fill_answers(answers)

        assert result == 1
        # Tried exactly two variants, stopped at first success.
        assert mock_click.call_count == 2
        called_args = [c.args[1] for c in mock_click.call_args_list]
        assert called_args[0] == "对"      # original first
        assert called_args[1] == "正确"    # next same-polarity variant
        # never crossed polarity
        assert "错" not in called_args and "B" not in called_args

    @patch("chaoxing.solvers.quiz.filler._detect_question_types")
    @patch("chaoxing.solvers.quiz.filler._fill_blank")
    @patch("chaoxing.solvers.quiz.filler._click_option")
    def test_judge_first_form_hit_no_extra_clicks(
        self, mock_click, mock_fill_blank, mock_detect
    ):
        """If the original judge form clicks immediately, no variants tried."""
        mock_detect.return_value = [
            {"index": 1, "type": "judge", "optionCount": 2,
             "hasTextarea": False, "hasCheckbox": False, "hasRadio": True},
        ]
        mock_click.side_effect = [True]  # original hits

        answers = [{"index": 1, "answer": "正确"}]
        result = _fill_answers(answers)

        assert result == 1
        mock_click.assert_called_once()  # stopped after the first form


# ── UNANSWERABLE_MARKERS ─────────────────────────────────────────

class TestUnanswerableMarkers:
    """Verify the unanswerable marker list is well-formed."""

    def test_all_markers_are_strings(self):
        """All markers should be strings."""
        for m in UNANSWERABLE_MARKERS:
            assert isinstance(m, str)

    def test_markers_are_lowercase(self):
        """All markers should be lowercase for case-insensitive matching."""
        for m in UNANSWERABLE_MARKERS:
            assert m == m.lower(), f"Marker '{m}' should be lowercase"

    def test_has_chinese_markers(self):
        """Should include Chinese-language markers."""
        assert "无法判断" in UNANSWERABLE_MARKERS
        assert "无法确定" in UNANSWERABLE_MARKERS
        assert "信息不足" in UNANSWERABLE_MARKERS

    def test_has_english_markers(self):
        """Should include English-language markers."""
        assert "unanswerable" in UNANSWERABLE_MARKERS
        assert "cannot determine" in UNANSWERABLE_MARKERS
        assert "not enough info" in UNANSWERABLE_MARKERS
