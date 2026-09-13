"""智慧树 M4 答题求解单元测试（纯逻辑，不起浏览器）。

覆盖：题型识别 / 答案归一 / 揭示字母解析 / 得分解析 / AI 入参组装 /
api 阶段与模式分发（solve_only 跳过视频、full 先视频后答题、grade_only
贯通、dry_run 早退不导航）。
"""

from pathlib import Path

import pytest

from platforms.zhihuishu.solvers.quiz import (
    ZhihuishuQuizSolver,
    build_ai_questions,
    detect_question_type,
    judge_answer_index,
    parse_answer_letters,
    parse_reveal_letters,
    parse_score,
)


class TestDetectQuestionType:
    def test_markers(self):
        assert detect_question_type("【单选题】", 4) == "single"
        assert detect_question_type("【多选题】", 4) == "multi"
        assert detect_question_type("【判断题】", 2) == "judge"
        assert detect_question_type("【填空题】", 0) == "fill"
        assert detect_question_type("【简答题】", 0) == "essay"

    def test_heuristic_two_options_is_judge(self):
        assert detect_question_type("", 2) == "judge"
        assert detect_question_type("", 4) == "single"
        assert detect_question_type(None, 5) == "single"


class TestParseAnswerLetters:
    def test_string_forms(self):
        assert parse_answer_letters("AC") == ["A", "C"]
        assert parse_answer_letters("A,C") == ["A", "C"]
        assert parse_answer_letters("a，c") == ["A", "C"]

    def test_list_form(self):
        assert parse_answer_letters(["A", "C"]) == ["A", "C"]

    def test_dedup_and_empty(self):
        assert parse_answer_letters("ABA") == ["A", "B"]
        assert parse_answer_letters("正确") == []
        assert parse_answer_letters(None) == []


class TestJudgeAnswerIndex:
    def test_mapping(self):
        assert judge_answer_index("正确") == 0
        assert judge_answer_index("对") == 0
        assert judge_answer_index("错误") == 1
        assert judge_answer_index("错") == 1

    def test_unparseable(self):
        assert judge_answer_index("B") == -1
        assert judge_answer_index([]) == -1


class TestParseScore:
    def test_patterns(self):
        assert parse_score("得分：90") == 90
        assert parse_score("成绩 88分") == 88
        assert parse_score("正确率 100 %") == 100

    def test_none(self):
        assert parse_score("") is None
        assert parse_score("无分数信息") is None


class TestBuildAiQuestions:
    def test_format(self):
        questions = [
            {"type": "single", "stem": "1+1=?",
             "options": ["1", "2", "3", "4"]},
            {"type": "judge", "stem": "天是蓝的", "options": ["对", "错"]},
        ]
        out = build_ai_questions(questions)
        assert out[0]["index"] == 1
        assert out[0]["text"].startswith("【single】1+1=?")
        assert "A. 1" in out[0]["text"] and "D. 4" in out[0]["text"]
        assert out[1]["text"].startswith("【judge】天是蓝的")


class TestParseRevealLetters:
    def test_reveal_text(self):
        assert parse_reveal_letters("正确答案：B") == ["B"]
        assert parse_reveal_letters("正确答案: A,C") == ["A", "C"]

    def test_no_reveal(self):
        assert parse_reveal_letters("") == []
        assert parse_reveal_letters("答案未揭示") == []


class TestSolverDryRun:
    def test_dry_run_returns_without_navigation(self, monkeypatch):
        """dry_run 进入即返回：任何导航/点击都不应发生。"""
        import platforms.zhihuishu.solvers.quiz as quiz_mod
        monkeypatch.setattr(quiz_mod, "pw_goto",
                            lambda *_a, **_k: pytest.fail("dry_run 不得导航"))
        solver = ZhihuishuQuizSolver(
            {"recruitId": "1", "courseId": "2", "name": "测试课"}, dry_run=True)
        assert solver.run() is True


class TestApiPhasesAndDispatch:
    """api._run_account 的模式分发与 grade_only/dry_run 贯通（mock 全 IO）。"""

    @pytest.fixture()
    def api_mod(self, monkeypatch):
        import platforms.zhihuishu.api as api
        calls = {"video": [], "quiz": []}

        class FakeVideoBot:
            def __init__(self, course):
                calls["video"].append(course["name"])

            def run(self):
                return True

        class FakeQuizSolver:
            def __init__(self, course, dry_run=False, grade_only=False):
                calls["quiz"].append(
                    {"course": course["name"],
                     "dry_run": dry_run, "grade_only": grade_only})

            def run(self):
                return True

        monkeypatch.setattr(api, "ensure_logged_in", lambda _idx: True)
        monkeypatch.setattr(api, "scan_courses", lambda: [
            {"name": "课A", "recruitId": "r1", "courseId": "c1"},
        ])
        # 不写真实 data/output，不真实 sleep
        monkeypatch.setattr(api, "_save_discovered",
                            lambda _idx, _courses: Path("dummy.json"))
        import time as _time
        monkeypatch.setattr(_time, "sleep", lambda *_a, **_k: 0.0)
        tree = {
            "chapters": [
                {"name": "第一章", "sections": [
                    {"kind": "video", "num": "1.1", "name": "导论",
                     "finished": False},
                ]},
            ],
            "quiz_sections": ["第一章测试"],
        }
        monkeypatch.setattr(api, "scan_course_sections", lambda *_a: tree)

        import platforms.zhihuishu.video as video_mod
        monkeypatch.setattr(video_mod, "ZhihuishuVideoBot", FakeVideoBot)
        # api 通过模块内 import 引用 solver：patch 源类
        import platforms.zhihuishu.solvers.quiz as quiz_mod
        monkeypatch.setattr(quiz_mod, "ZhihuishuQuizSolver", FakeQuizSolver)
        api._calls = calls
        return api

    @staticmethod
    def _config(api, mode, **kw):
        return api.RunConfig(mode=mode, **kw)

    def test_valid_phases_include_solve_quiz(self):
        import platforms.zhihuishu.api as api
        assert "solve_quiz" in api.VALID_PHASES

    def test_solve_only_skips_video_runs_quiz(self, api_mod):
        ok = api_mod.run_account(0, {}, self._config(api_mod, "solve_only"))
        assert ok is True
        assert api_mod._calls["video"] == []
        assert len(api_mod._calls["quiz"]) == 1
        assert api_mod._calls["quiz"][0]["course"] == "课A"

    def test_full_runs_video_then_quiz(self, api_mod):
        ok = api_mod.run_account(0, {}, self._config(api_mod, "full"))
        assert ok is True
        assert api_mod._calls["video"] == ["课A"]
        assert len(api_mod._calls["quiz"]) == 1

    def test_grade_only_and_dry_run_plumb_through(self, api_mod):
        api_mod.run_account(0, {}, self._config(
            api_mod, "solve_only", grade_only=True, dry_run=True))
        assert api_mod._calls["quiz"][0]["grade_only"] is True
        assert api_mod._calls["quiz"][0]["dry_run"] is True

    def test_scan_only_runs_neither(self, api_mod):
        ok = api_mod.run_account(0, {}, self._config(api_mod, "scan_only"))
        assert ok is True
        assert api_mod._calls["video"] == []
        assert api_mod._calls["quiz"] == []
