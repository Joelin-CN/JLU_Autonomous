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
    judge_answer_text,
    map_answer_to_letters,
    parse_answer_letters,
    parse_reveal_letters,
    parse_score,
    sanitize_fill_text,
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


class TestJudgeAnswerText:
    def test_mapping(self):
        assert judge_answer_text("正确") == "对"
        assert judge_answer_text("对") == "对"
        assert judge_answer_text("错误") == "错"
        assert judge_answer_text("错") == "错"

    def test_unparseable(self):
        assert judge_answer_text("B") == ""
        assert judge_answer_text([]) == ""


class TestMapAnswerToLetters:
    """选项随机排列（真机实测页面明示），AI 答案须按选项内容/字母映射。"""

    def test_choice_letters_intersect_available(self):
        # AI 答 AC，页面只有 A/B/D（C 不存在）→ 只点 A
        assert map_answer_to_letters("AC", "single",
                                     ["A", "B", "D"], ["x", "y", "z"]) == ["A"]

    def test_judge_maps_by_option_text(self):
        # 判断题选项随机：A=错 B=对；AI 答「正确」→ B
        assert map_answer_to_letters("正确", "judge",
                                     ["A", "B"], ["错", "对"]) == ["B"]
        assert map_answer_to_letters("错误", "judge",
                                     ["A", "B"], ["错", "对"]) == ["A"]

    def test_no_match(self):
        assert map_answer_to_letters(None, "judge", ["A", "B"], ["对", "错"]) == []
        assert map_answer_to_letters("Z", "single", ["A", "B"], ["x", "y"]) == []


class TestSanitizeFillText:
    def test_takes_first_line_and_strips(self):
        # AI 可能附带解释——只取首行
        assert sanitize_fill_text("CMOS\n解析：因为...") == "CMOS"
        assert sanitize_fill_text("  触发器  ") == "触发器"

    def test_list_and_none(self):
        assert sanitize_fill_text(["a", "b"]) == "a、b"
        assert sanitize_fill_text(None) == ""

    def test_length_cap(self):
        assert len(sanitize_fill_text("x" * 900)) == 500


class TestParseScore:
    def test_patterns(self):
        assert parse_score("得分：90") == 90
        assert parse_score("成绩 88分") == 88
        assert parse_score("正确率 100 %") == 100

    def test_score_dialog_takes_priority(self):
        # 真机提交弹窗文本；通用「N分」会误匹配题目标记「(2分)」——成绩模式优先
        assert parse_score("你本次获得的成绩是 20 分 总分数 20 (2分)") == 20

    def test_none(self):
        assert parse_score("") is None
        assert parse_score("无分数信息") is None


class TestBuildAiQuestions:
    def test_format(self):
        """format_quiz_text_prompt 消费 {index, question, options} 结构。"""
        questions = [
            {"type": "single", "stem": "1+1=?",
             "options": ["1", "2", "3", "4"]},
            {"type": "judge", "stem": "天是蓝的", "options": ["对", "错"]},
        ]
        out = build_ai_questions(questions)
        assert out[0]["index"] == 1
        assert out[0]["question"].startswith("【single】1+1=?")
        assert out[0]["options"][0] == "A. 1"
        assert out[0]["options"][3] == "D. 4"
        assert out[1]["question"].startswith("【judge】天是蓝的")
        # 直接喂给 format_quiz_text_prompt 应产出含题干与选项的 prompt
        from core.ai.prompts import format_quiz_text_prompt
        prompt = format_quiz_text_prompt(out, "测试课", "冒烟")
        assert "1+1=?" in prompt and "A. 1" in prompt


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

    def test_generic_runner_config_without_mode_attr(self, api_mod):
        """生产路径回归：core.orchestrator 构造 config 只传布尔不传 mode——
        真机实测曾因此永远进不了答题分支（读 config.mode 旧默认 scan_only）。
        RunConfig 现双向自洽：只传布尔 → mode/flags 齐全。"""
        cfg = api_mod.RunConfig(scan_only=False, quiz_only=True, grade_only=True)
        assert cfg.mode == "solve_only" and cfg.quiz_only and not cfg.scan_only
        ok = api_mod.run_account(0, {}, cfg)
        assert ok is True
        assert api_mod._calls["video"] == []
        assert len(api_mod._calls["quiz"]) == 1
        assert api_mod._calls["quiz"][0]["grade_only"] is True

    def test_run_config_mode_only_derives_flags(self, api_mod):
        """直接构造只传 mode → flags 反向推导齐全。"""
        cfg = api_mod.RunConfig(mode="solve_only")
        assert cfg.quiz_only and not cfg.scan_only
        cfg2 = api_mod.RunConfig(mode="full")
        assert not cfg2.quiz_only and not cfg2.scan_only


class TestFilterCourses:
    def test_no_filter_passthrough(self):
        from platforms.zhihuishu.api import filter_courses
        cs = [{"name": "课A", "recruitId": "r1", "courseId": "c1"}]
        assert filter_courses(cs, None) == cs
        assert filter_courses(cs, "") == cs

    def test_match_by_name_or_ids(self):
        from platforms.zhihuishu.api import filter_courses
        cs = [
            {"name": "数字集成电路设计基础", "recruitId": "428215", "courseId": "1000003834"},
            {"name": "其他课", "recruitId": "r2", "courseId": "c2"},
        ]
        assert filter_courses(cs, "428215") == [cs[0]]
        assert filter_courses(cs, "数字集成电路") == [cs[0]]
        assert filter_courses(cs, "c2") == [cs[1]]
        assert filter_courses(cs, "428215,c2") == cs

    def test_no_match_empty(self):
        from platforms.zhihuishu.api import filter_courses
        assert filter_courses([{"name": "x", "recruitId": "r", "courseId": "c"}], "zzz") == []


class TestCoursesMapping:
    def test_course_id_and_progress(self):
        from platforms.zhihuishu.courses import _map_course, _parse_progress
        c = _map_course({"courseId": "1000003834", "recruitId": "428215",
                         "name": "数字集成电路", "progress": "2%",
                         "total_sections": 3, "remaining_sections": [],
                         "quiz_sections": []}, 0)
        assert c["id"] == "1000003834"          # 渲染层不再拿 undefined
        assert c["progress"] == 2                # "2%" → 2（NaN% 修复）
        assert _parse_progress(None) == 0
        assert _parse_progress("37%") == 37
        # id 兜底链
        assert _map_course({"recruitId": "r", "name": "n"}, 0)["id"] == "r"
        assert _map_course({"name": "n"}, 0)["id"] == "n"
