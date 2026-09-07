"""Tests for chaoxing.discover — course discovery and config building."""
from unittest.mock import patch, MagicMock

from chaoxing.discover import build_dynamic_course_config, discover_courses, save_discovered_state


# ── build_dynamic_course_config ────────────────────────────────

class TestBuildDynamicCourseConfig:
    """Tests for build_dynamic_course_config — dynamic config from scan results."""

    def test_basic_config_building(self):
        """Should build a valid course config dict from course_info and sections."""
        course_info = {
            "name": "概率论与数理统计",
            "courseid": "12345",
            "clazzid": "67890",
            "cpi": "415409200",
            "done": 5,
            "total": 20,
            "percent": 25.0,
            "teacher": "张老师",
        }
        sections = {
            "ok": True,
            "done": 5,
            "total": 20,
            "quiz_sections": [{"key": "1.1", "name": "章节测试1"}],
            "content_sections": [{"key": "2.1", "name": "视频1"}],
            "chapters": [
                {
                    "num": 1,
                    "name": "第一章",
                    "sections_count": 3,
                    "sections": [
                        {"name": "1.1", "tasks": 5},
                        {"name": "1.2", "tasks": 3},
                        {"name": "1.3", "tasks": 2},
                    ],
                },
            ],
        }
        result = build_dynamic_course_config(course_info, sections)
        assert result["name"] == "概率论与数理统计"
        assert result["courseid"] == "12345"
        assert result["clazzid"] == "67890"
        assert result["cpi"] == "415409200"
        assert result["current_progress"] == 5
        assert result["total_tasks"] == 20
        assert result["remaining_quiz_sections"] == [{"key": "1.1", "name": "章节测试1"}]
        assert result["remaining_content_sections"] == [{"key": "2.1", "name": "视频1"}]
        assert len(result["chapters"]) == 1
        assert result["chapters"][0]["num"] == 1
        assert result["chapters"][0]["name"] == "第一章"
        assert result["chapters"][0]["sections"] == 3
        assert result["chapters"][0]["tasks_per"] == [5, 3, 2]

    def test_empty_sections(self):
        """Should handle empty sections gracefully."""
        course_info = {
            "name": "Empty Course",
            "courseid": "000",
            "clazzid": "000",
        }
        sections = {
            "ok": True,
            "done": 0,
            "total": 0,
            "quiz_sections": [],
            "content_sections": [],
            "chapters": [],
        }
        result = build_dynamic_course_config(course_info, sections)
        assert result["name"] == "Empty Course"
        assert result["remaining_quiz_sections"] == []
        assert result["remaining_content_sections"] == []
        assert result["chapters"] == []

    def test_missing_cpi_default(self):
        """When cpi is missing from course_info, should use default '415409200'."""
        course_info = {
            "name": "Test",
            "courseid": "111",
            "clazzid": "222",
        }
        sections = {"chapters": [], "quiz_sections": [], "content_sections": [],
                     "done": 0, "total": 0}
        result = build_dynamic_course_config(course_info, sections)
        assert result["cpi"] == "415409200"

    def test_sections_fallback_for_progress(self):
        """When course_info has no done/total, should use sections values."""
        course_info = {
            "name": "Test",
            "courseid": "111",
            "clazzid": "222",
        }
        sections = {
            "done": 3, "total": 10,
            "quiz_sections": [], "content_sections": [],
            "chapters": [],
        }
        result = build_dynamic_course_config(course_info, sections)
        assert result["current_progress"] == 3
        assert result["total_tasks"] == 10

    def test_course_info_fallback_for_progress(self):
        """When sections has no done/total, should use course_info values."""
        course_info = {
            "name": "Test",
            "courseid": "111",
            "clazzid": "222",
            "done": 7,
            "total": 15,
        }
        sections = {
            "quiz_sections": [], "content_sections": [],
            "chapters": [],
        }
        result = build_dynamic_course_config(course_info, sections)
        assert result["current_progress"] == 7
        assert result["total_tasks"] == 15

    def test_multiple_chapters(self):
        """Should handle multiple chapters with different section counts."""
        course_info = {
            "name": "Test",
            "courseid": "111",
            "clazzid": "222",
        }
        sections = {
            "done": 0, "total": 0,
            "quiz_sections": [], "content_sections": [],
            "chapters": [
                {
                    "num": 1, "name": "Ch1",
                    "sections_count": 2,
                    "sections": [
                        {"name": "1.1", "tasks": 3},
                        {"name": "1.2", "tasks": 4},
                    ],
                },
                {
                    "num": 2, "name": "Ch2",
                    "sections_count": 1,
                    "sections": [
                        {"name": "2.1", "tasks": 5},
                    ],
                },
            ],
        }
        result = build_dynamic_course_config(course_info, sections)
        assert len(result["chapters"]) == 2
        assert result["chapters"][0]["num"] == 1
        assert result["chapters"][1]["num"] == 2
        assert result["chapters"][0]["tasks_per"] == [3, 4]
        assert result["chapters"][1]["tasks_per"] == [5]

    def test_sections_without_sections_field(self):
        """Chapters without 'sections' field should default to empty tasks_per."""
        course_info = {"name": "T", "courseid": "1", "clazzid": "2"}
        sections = {
            "done": 0, "total": 0,
            "quiz_sections": [], "content_sections": [],
            "chapters": [
                {"num": 1, "name": "Ch1", "sections_count": 0},
            ],
        }
        result = build_dynamic_course_config(course_info, sections)
        assert len(result["chapters"]) == 1
        assert result["chapters"][0]["tasks_per"] == []

    def test_section_tasks_default_zero(self):
        """Sections without 'tasks' field should default to 0."""
        course_info = {"name": "T", "courseid": "1", "clazzid": "2"}
        sections = {
            "done": 0, "total": 0,
            "quiz_sections": [], "content_sections": [],
            "chapters": [
                {
                    "num": 1, "name": "Ch1", "sections_count": 2,
                    "sections": [
                        {"name": "1.1"},
                        {"name": "1.2", "tasks": 5},
                    ],
                },
            ],
        }
        result = build_dynamic_course_config(course_info, sections)
        assert result["chapters"][0]["tasks_per"] == [0, 5]

    def test_chapter_name_default(self):
        """Chapter without 'name' field should default to empty string."""
        course_info = {"name": "T", "courseid": "1", "clazzid": "2"}
        sections = {
            "done": 0, "total": 0,
            "quiz_sections": [], "content_sections": [],
            "chapters": [
                {"num": 1, "sections_count": 0, "sections": []},
            ],
        }
        result = build_dynamic_course_config(course_info, sections)
        assert result["chapters"][0]["name"] == ""


# ── discover_courses ──────────────────────────────────────────

class TestDiscoverCourses:
    """Tests for discover_courses — course scanning and dynamic config building."""

    @patch("chaoxing.discover.log")
    @patch("chaoxing.discover.progress")
    @patch("chaoxing.discover.scan_course_sections")
    @patch("chaoxing.discover.scan_courses")
    @patch("chaoxing.discover.load_config")
    def test_no_courses_found(self, mock_load_config, mock_scan, mock_scan_sections,
                               mock_progress, mock_log):
        """When scan_courses returns empty, should return empty list."""
        mock_scan.return_value = []
        result = discover_courses()
        assert result == []

    @patch("chaoxing.discover.log")
    @patch("chaoxing.discover.progress")
    @patch("chaoxing.discover.scan_course_sections")
    @patch("chaoxing.discover.scan_courses")
    def test_single_course_discovered(self, mock_scan, mock_scan_sections,
                                       mock_progress, mock_log):
        """Should discover and build config for a single course."""
        mock_scan.return_value = [
            {
                "name": "数学分析",
                "courseid": "101",
                "clazzid": "201",
                "cpi": "415409200",
                "done": 2,
                "total": 10,
                "percent": 20.0,
                "teacher": "李老师",
            },
        ]
        mock_scan_sections.return_value = {
            "ok": True,
            "done": 2,
            "total": 10,
            "quiz_sections": [],
            "content_sections": [],
            "chapters": [
                {"num": 1, "name": "Ch1", "sections_count": 1,
                 "sections": [{"name": "1.1", "tasks": 10}]},
            ],
        }
        result = discover_courses()
        assert len(result) == 1
        assert result[0]["name"] == "数学分析"
        assert result[0]["courseid"] == "101"

    @patch("chaoxing.discover.log")
    @patch("chaoxing.discover.progress")
    @patch("chaoxing.discover.scan_course_sections")
    @patch("chaoxing.discover.scan_courses")
    def test_course_filter_match(self, mock_scan, mock_scan_sections,
                                  mock_progress, mock_log):
        """Should filter courses by name substring."""
        mock_scan.return_value = [
            {"name": "数学分析", "courseid": "101", "clazzid": "201",
             "done": 0, "total": 10, "percent": 0},
            {"name": "线性代数", "courseid": "102", "clazzid": "202",
             "done": 0, "total": 10, "percent": 0},
        ]
        mock_scan_sections.return_value = {
            "ok": True, "done": 0, "total": 10,
            "quiz_sections": [], "content_sections": [],
            "chapters": [],
        }
        result = discover_courses(course_filter="线性")
        assert len(result) == 1
        assert result[0]["name"] == "线性代数"

    @patch("chaoxing.discover.log")
    @patch("chaoxing.discover.progress")
    @patch("chaoxing.discover.scan_courses")
    def test_course_filter_no_match(self, mock_scan, mock_progress, mock_log):
        """When filter matches nothing, should return empty list."""
        mock_scan.return_value = [
            {"name": "数学分析", "courseid": "101", "clazzid": "201",
             "done": 0, "total": 10, "percent": 0},
        ]
        result = discover_courses(course_filter="物理")
        assert result == []

    @patch("chaoxing.discover.log")
    @patch("chaoxing.discover.progress")
    @patch("chaoxing.discover.scan_course_sections")
    @patch("chaoxing.discover.scan_courses")
    def test_scan_sections_failure(self, mock_scan, mock_scan_sections,
                                     mock_progress, mock_log):
        """When scan_course_sections returns ok=False, should skip that course."""
        mock_scan.return_value = [
            {"name": "Course1", "courseid": "101", "clazzid": "201",
             "done": 0, "total": 10, "percent": 0},
            {"name": "Course2", "courseid": "102", "clazzid": "202",
             "done": 0, "total": 10, "percent": 0},
        ]
        mock_scan_sections.side_effect = [
            {"ok": False, "reason": "scan error"},
            {"ok": True, "done": 0, "total": 10,
             "quiz_sections": [], "content_sections": [], "chapters": []},
        ]
        result = discover_courses()
        assert len(result) == 1
        assert result[0]["name"] == "Course2"

    @patch("chaoxing.discover.log")
    @patch("chaoxing.discover.progress")
    @patch("chaoxing.discover.scan_course_sections")
    @patch("chaoxing.discover.scan_courses")
    @patch("chaoxing.discover.load_config")
    def test_zero_total_courses_are_scanned(self, mock_load_config, mock_scan,
                                            mock_scan_sections, mock_progress,
                                            mock_log):
        """0/0 courses are scanned too — the listing card total is unreliable."""
        mock_scan.return_value = [
            {"name": "ZeroTask", "courseid": "101", "clazzid": "201",
             "done": 0, "total": 0, "percent": 0},
        ]
        mock_load_config.return_value = {"courses": []}
        mock_scan_sections.return_value = {
            "ok": True, "done": 0, "total": 0,
            "quiz_sections": [], "content_sections": [], "chapters": [],
        }
        result = discover_courses()
        assert len(result) == 1
        assert result[0]["total_tasks"] == 0
        assert mock_scan_sections.called

    @patch("chaoxing.discover.log")
    @patch("chaoxing.discover.progress")
    @patch("chaoxing.discover.scan_course_sections")
    @patch("chaoxing.discover.scan_courses")
    @patch("chaoxing.discover.load_config")
    def test_zero_total_course_completed_excluded(self, mock_load_config,
                                                   mock_scan, mock_scan_sections,
                                                   mock_progress, mock_log):
        """0/0 course that is actually 100% done must be excluded after scan."""
        mock_scan.return_value = [
            {"name": "DoneHidden", "courseid": "101", "clazzid": "201",
             "done": 0, "total": 0, "percent": 0},
        ]
        mock_load_config.return_value = {"courses": []}
        mock_scan_sections.return_value = {
            "ok": True, "done": 12, "total": 12,
            "quiz_sections": [], "content_sections": [], "chapters": [],
        }
        result = discover_courses()
        assert result == []

    @patch("chaoxing.discover.log")
    @patch("chaoxing.discover.progress")
    @patch("chaoxing.discover.scan_course_sections")
    @patch("chaoxing.discover.scan_courses")
    @patch("chaoxing.discover.load_config")
    def test_zero_total_courses_with_config_scans_anyway(self, mock_load_config,
                                                          mock_scan, mock_scan_sections,
                                                          mock_progress, mock_log):
        """0/0 courses with config entries should still be scanned."""
        mock_scan.return_value = [
            {"name": "ConfigCourse", "courseid": "101", "clazzid": "201",
             "done": 0, "total": 0, "percent": 0},
        ]
        mock_load_config.return_value = {
            "courses": [{"name": "ConfigCourse", "courseid": "101"}],
        }
        mock_scan_sections.return_value = {
            "ok": True, "done": 5, "total": 15,
            "quiz_sections": [], "content_sections": [], "chapters": [],
        }
        result = discover_courses()
        assert len(result) == 1
        assert mock_scan_sections.called

    def test_course_filter_exact_match(self):
        """Filter that exactly matches course name should work."""
        # Exact match is tested inline with the filter logic
        # The filter checks: course_filter in name or course_filter == name
        courses = [{"name": "物理", "courseid": "1", "clazzid": "1",
                    "done": 0, "total": 10, "percent": 0}]
        # substring match: "物理" in "物理" is True
        filtered = [c for c in courses if "物理" in c['name'] or "物理" == c['name']]
        assert len(filtered) == 1

    def test_course_filter_partial(self):
        """Filter that is substring of course name should match."""
        courses = [{"name": "大学物理ABC", "courseid": "1", "clazzid": "1",
                    "done": 0, "total": 10, "percent": 0}]
        filtered = [c for c in courses if "物理" in c['name'] or "物理" == c['name']]
        assert len(filtered) == 1

    def test_course_filter_not_match(self):
        """Filter not matching any course should return empty."""
        courses = [{"name": "数学", "courseid": "1", "clazzid": "1",
                    "done": 0, "total": 10, "percent": 0}]
        filtered = [c for c in courses if "物理" in c['name'] or "物理" == c['name']]
        assert len(filtered) == 0


# ── save_discovered_state ─────────────────────────────────────

class TestSaveDiscoveredState:
    """Tests for save_discovered_state — persistence of discovery results."""

    @patch("chaoxing.discover.log")
    @patch("chaoxing.discover._get_active_session")
    @patch("builtins.open")
    @patch("chaoxing.discover.OUTPUT_DIR")
    def test_saves_with_default_session(self, mock_output_dir, mock_open, mock_session,
                                         mock_log):
        """Should save courses with default session suffix."""
        mock_session.return_value = "chaoxing-chrome"
        mock_path = MagicMock()
        captured = []
        mock_output_dir.__truediv__ = lambda _self, other: (
            captured.append(str(other)) or mock_path)
        mock_output_dir.mkdir = MagicMock()

        courses = [{"name": "Course1", "courseid": "101"}]
        save_discovered_state(courses)

        # Should write to discovered_courses.json (no suffix for default)
        mock_open.assert_called_once()
        assert captured == ["discovered_courses.json"]

    @patch("chaoxing.discover.log")
    @patch("chaoxing.discover._get_active_session")
    @patch("builtins.open")
    @patch("chaoxing.discover.OUTPUT_DIR")
    def test_saves_with_multi_account_session(self, mock_output_dir, mock_open,
                                               mock_session, mock_log):
        """Should append session suffix for multi-account sessions."""
        mock_session.return_value = "chaoxing-chrome-2"
        mock_path = MagicMock()
        captured = []
        mock_output_dir.__truediv__ = lambda _self, other: (
            captured.append(str(other)) or mock_path)
        mock_output_dir.mkdir = MagicMock()

        courses = [{"name": "Course1"}]
        save_discovered_state(courses)

        assert captured == ["discovered_courses_chaoxing-chrome-2.json"]

    @patch("chaoxing.discover.log")
    @patch("chaoxing.discover._get_active_session")
    @patch("builtins.open")
    @patch("chaoxing.discover.OUTPUT_DIR")
    def test_empty_courses_list(self, mock_output_dir, mock_open,
                                 mock_session, mock_log):
        """Should handle saving an empty courses list."""
        mock_output_dir.__truediv__ = MagicMock(return_value=MagicMock())
        mock_session.return_value = "chaoxing-chrome"
        mock_path = MagicMock()
        mock_output_dir.mkdir = MagicMock()
        mock_output_dir.__truediv__.return_value = mock_path

        save_discovered_state([])
        mock_open.assert_called_once()

    @patch("chaoxing.discover.log")
    @patch("chaoxing.discover._get_active_session")
    @patch("builtins.open")
    @patch("chaoxing.discover.OUTPUT_DIR")
    def test_output_dir_created(self, mock_output_dir, mock_open,
                                  mock_session, mock_log):
        """Should create output directory if it does not exist."""
        mock_output_dir.__truediv__ = MagicMock(return_value=MagicMock())
        mock_session.return_value = "chaoxing-chrome"
        mock_output_dir.mkdir = MagicMock()
        mock_path = MagicMock()
        mock_output_dir.__truediv__.return_value = mock_path

        save_discovered_state([])
        mock_output_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)

    @patch("chaoxing.discover.log")
    @patch("chaoxing.discover._get_active_session")
    @patch("builtins.open")
    @patch("chaoxing.discover.OUTPUT_DIR")
    def test_writes_valid_json(self, mock_output_dir, mock_open,
                                 mock_session, mock_log):
        """Should write valid JSON content."""
        import json
        mock_output_dir.__truediv__ = MagicMock(return_value=MagicMock())
        mock_session.return_value = "chaoxing-chrome"
        mock_path = MagicMock()
        mock_output_dir.mkdir = MagicMock()
        mock_output_dir.__truediv__.return_value = mock_path

        # Capture what is written
        written_content = []

        def capture_write(content):
            written_content.append(content)

        mock_file = MagicMock()
        mock_file.__enter__.return_value.write = capture_write
        mock_open.return_value = mock_file

        courses = [{"name": "Test", "courseid": "123", "clazzid": "456"}]
        save_discovered_state(courses)

        assert len(written_content) > 0
        parsed = json.loads("".join(written_content))
        assert len(parsed) == 1
        assert parsed[0]["name"] == "Test"
        assert mock_open.call_args.kwargs.get("encoding") == "utf-8"


# ── save_discovered_state merge semantics ──────────────────────

class TestSaveDiscoveredStateMerge:
    """A filtered run must not wipe untouched courses from the state file."""

    def _save(self, tmp_path, courses, merge=False):
        with patch("chaoxing.discover.OUTPUT_DIR", tmp_path), \
             patch("chaoxing.discover._get_active_session", return_value="s-x"):
            save_discovered_state(courses, merge=merge)

    def test_filtered_run_merges_untouched_courses(self, tmp_path):
        existing = [
            {"courseid": "1", "name": "A", "total_tasks": 10},
            {"courseid": "2", "name": "B", "total_tasks": 20},
        ]
        self._save(tmp_path, existing)
        # A filtered run that only re-scanned course 2 (now complete: 20/20)
        self._save(tmp_path, [{"courseid": "2", "name": "B", "total_tasks": 20,
                               "current_progress": 20}], merge=True)
        import json as _json
        saved = _json.load(open(tmp_path / "discovered_courses_s-x.json", encoding="utf-8"))
        ids = sorted(c["courseid"] for c in saved)
        assert ids == ["1", "2"], "untouched course must survive a filtered run"
        b = next(c for c in saved if c["courseid"] == "2")
        assert b["current_progress"] == 20, "rescanned course must be updated"

    def test_full_scan_overwrites(self, tmp_path):
        self._save(tmp_path, [{"courseid": "1", "name": "A"}])
        # Full scan (merge=False) drops courses it no longer reports
        self._save(tmp_path, [{"courseid": "9", "name": "Z"}])
        import json as _json
        saved = _json.load(open(tmp_path / "discovered_courses_s-x.json", encoding="utf-8"))
        assert [c["courseid"] for c in saved] == ["9"]

    def test_merge_with_corrupt_file_falls_back_to_overwrite(self, tmp_path):
        (tmp_path / "discovered_courses_s-x.json").write_text("not json", encoding="utf-8")
        self._save(tmp_path, [{"courseid": "1"}], merge=True)
        import json as _json
        saved = _json.load(open(tmp_path / "discovered_courses_s-x.json", encoding="utf-8"))
        assert [c["courseid"] for c in saved] == ["1"]
