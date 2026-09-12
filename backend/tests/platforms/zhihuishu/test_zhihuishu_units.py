"""智慧树平台单元测试：XOR 编码向量 / 凭据解析回写 / 章节树组装。"""

import json
from pathlib import Path

import pytest

from platforms.zhihuishu.constants import (
    encode_recruit_and_course_id, build_study_url,
)
from platforms.zhihuishu.scanner import _build_tree
from core.credentials import parse_credential_block


class TestXorEncoder:
    """2026-09-12 实地破译的编码向量（调研报告 §Q2）。"""

    def test_known_vector(self):
        assert encode_recruit_and_course_id("428215", "1000003834") == \
            "4e5a515a445c4859454a5859584651405c"

    def test_known_vector_prefix(self):
        # 逐字节抽样：'4'^'z'=0x34, '2'^'h'=0x32, '8'^'i'=0x38, ';'^'s'=0x3b
        out = encode_recruit_and_course_id("428215", "1000003834")
        assert out[:8] == "4e5a515a"

    def test_study_url(self):
        url = build_study_url("428215", "1000003834")
        assert url.startswith(
            "https://studyvideoh5.zhihuishu.com/stuStudy?recruitAndCourseId=")
        assert url.endswith(encode_recruit_and_course_id("428215", "1000003834"))

    def test_key_cycles(self):
        # 超过密钥长度后继续循环（无异常、输出为偶数长度 hex）
        out = encode_recruit_and_course_id("12345678901234", "567890123456789")
        assert len(out) % 2 == 0


class TestCredentialParsing:
    def test_block_with_website(self):
        block = "{\nwebsite: https://login.zhihuishu.com/?origin=zhs\naccount[0]: 13200003918\npassword[0]: example\n}"
        cred = parse_credential_block(block)
        assert cred == {
            "account": "13200003918", "password": "example",
            "website": "https://login.zhihuishu.com/?origin=zhs", "index": 0,
        }

    def test_block_chinese_aliases(self):
        block = "{\n账号[1]: 13200003919\n密码[1]: example\n}"
        cred = parse_credential_block(block, default_website="https://x")
        assert cred["index"] == 1
        assert cred["website"] == "https://x"

    def test_block_incomplete(self):
        assert parse_credential_block("{\naccount[0]: 13200003918\n}") is None


class TestBuildTree:
    def test_assembly(self):
        items = [
            {"kind": "chapter", "num": "绪章", "name": "绪论"},
            {"kind": "video", "num": "0.1", "name": "数字集成电路简介",
             "duration": "00:07:36", "current": True, "finished": False},
            {"kind": "quiz", "name": " 平时测试 "},
            {"kind": "chapter", "num": "第一章", "name": "MOSFET器件物理基础"},
            {"kind": "video", "num": "1.1", "name": "MOSFET结构与工作原理",
             "duration": "00:05:25", "finished": True},
        ]
        tree = _build_tree(items)
        assert len(tree["chapters"]) == 2
        assert tree["chapters"][0]["name"] == "绪论"
        assert tree["chapters"][0]["sections"][0]["num"] == "0.1"
        assert tree["chapters"][0]["sections"][1]["kind"] == "quiz"
        assert tree["chapters"][1]["sections"][0]["finished"] is True
        assert tree["quiz_sections"] == ["绪论"]

    def test_video_before_chapter_gets_root_bucket(self):
        tree = _build_tree([{"kind": "video", "num": "0.1", "name": "x",
                             "duration": "", "finished": False}])
        assert len(tree["chapters"]) == 1
        assert tree["chapters"][0]["sections"][0]["name"] == "x"
        assert tree["quiz_sections"] == []


class TestAccountsRoundtrip:
    def test_zhihuishu_creds_file_reads(self, monkeypatch, tmp_path):
        f = tmp_path / "zhihuishu.txt"
        f.write_text(
            "{\nwebsite: https://login.zhihuishu.com/?origin=zhs\n"
            "account[0]: 13200003918\npassword[0]: example\n}\n",
            encoding="utf-8")
        monkeypatch.setenv("ZHIHUISHU_ACCOUNTS_FILE", str(f))
        from platforms.zhihuishu.auth import read_all_zhihuishu_credentials
        creds = read_all_zhihuishu_credentials()
        assert len(creds) == 1
        assert creds[0]["account"] == "13200003918"
        assert creds[0]["website"].startswith("https://login.zhihuishu.com")


def test_api_module_protocol_phases():
    import platforms.zhihuishu.api as zapi
    assert "scan_courses" in zapi.VALID_PHASES
    assert "idle" in zapi.VALID_PHASES
