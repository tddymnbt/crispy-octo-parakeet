"""Tests for the resilient Gemini JSON parser in scripts/analyze_repos.py."""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import analyze_repos  # noqa: E402


def gemini_response(text):
    """Build a synthetic Gemini interaction response wrapping ``text``."""
    return {
        "steps": [
            {
                "type": "model_output",
                "content": [{"type": "text", "text": text}],
            }
        ]
    }


class ParserTests(unittest.TestCase):
    def test_valid_json(self):
        self.assertEqual(analyze_repos.parse_json('{"summary":"hello"}'), {"summary": "hello"})

    def test_markdown_fenced_json(self):
        raw = '```json\n{"summary":"hello"}\n```'
        self.assertEqual(analyze_repos.parse_json(raw), {"summary": "hello"})

    def test_markdown_fence_without_json_language_tag(self):
        raw = '```\n{"summary":"hello"}\n```'
        self.assertEqual(analyze_repos.parse_json(raw), {"summary": "hello"})

    def test_tilde_fenced_json(self):
        raw = '~~~json\n{"summary":"hello"}\n~~~'
        self.assertEqual(analyze_repos.parse_json(raw), {"summary": "hello"})

    def test_json_surrounded_by_prose(self):
        raw = "Here is the analysis:\n\n{\"summary\":\"hello\"}\n\nI hope this helps!"
        self.assertEqual(analyze_repos.parse_json(raw), {"summary": "hello"})

    def test_valid_escaped_content(self):
        raw = '{"summary":"line1\\nline2"}'
        self.assertEqual(analyze_repos.parse_json(raw), {"summary": "line1\nline2"})

    def test_invalid_escape_underscore(self):
        raw = '{"summary":"something \\_ unusual"}'
        parsed = analyze_repos.parse_json(raw)
        self.assertEqual(parsed["summary"], "something \\_ unusual")

    def test_invalid_escape_paren_and_d(self):
        self.assertEqual(
            analyze_repos.parse_json('{"summary":"a \\( b \\d"}')["summary"], "a \\( b \\d"
        )

    def test_windows_style_path(self):
        raw = '{"path":"C:\\\\Users\\\\Public"}'
        self.assertEqual(analyze_repos.parse_json(raw), {"path": "C:\\Users\\Public"})

    def test_regex_like_string(self):
        # Unescaped backslashes inside a string are made safe, not removed.
        raw = '{"regex":"\\d+\\s+\\w+"}'
        self.assertEqual(analyze_repos.parse_json(raw)["regex"], "\\d+\\s+\\w+")

    def test_escaped_quotes_preserved(self):
        raw = '{"quote":"He said \\"hi\\""}'
        self.assertEqual(analyze_repos.parse_json(raw), {"quote": 'He said "hi"'})

    def test_url_with_slashes(self):
        raw = '{"url":"https://github.com/owner/repo"}'
        self.assertEqual(analyze_repos.parse_json(raw), {"url": "https://github.com/owner/repo"})

    def test_nested_json_not_truncated(self):
        raw = '{"outer":{"inner":[{"a":1},{"b":2}],"deep":{"c":[3,4]}}}'
        self.assertEqual(
            analyze_repos.parse_json(raw),
            {"outer": {"inner": [{"a": 1}, {"b": 2}], "deep": {"c": [3, 4]}}},
        )

    def test_prose_around_nested_json(self):
        raw = 'Words before {"a":{"b":["x","y"]}} and words after.'
        self.assertEqual(analyze_repos.parse_json(raw), {"a": {"b": ["x", "y"]}})

    def test_json_array_extraction(self):
        raw = 'prose [{"a":1}, {"b":"]"}] prose'
        self.assertEqual(analyze_repos.parse_json(raw), [{"a": 1}, {"b": "]"}])


    def test_completely_invalid_response_raises(self):
        with self.assertRaises(analyze_repos.GeminiJsonParseError):
            analyze_repos.parse_json("This is not JSON at all.")

    def test_empty_response_raises(self):
        with self.assertRaises(analyze_repos.GeminiJsonParseError):
            analyze_repos.parse_json("")

    def test_valid_json_is_untouched(self):
        raw = '{"summary":"hello"}'
        result = analyze_repos.parse_json(raw)
        # A plain, already-valid payload parses first without transformation.
        self.assertEqual(result, {"summary": "hello"})


class EscapeRepairTests(unittest.TestCase):
    def test_valid_escapes_preserved(self):
        raw = '{"a":"tab\\t newline\\n quote\\""}'
        out = analyze_repos.repair_invalid_json_escapes(raw)
        self.assertIn("\\t", out)
        self.assertIn("\\n", out)
        self.assertIn('\\"', out)

    def test_invalid_escape_turned_into_literal_backslash(self):
        raw = '{"a":"x \\_ y"}'
        out = analyze_repos.repair_invalid_json_escapes(raw)
        self.assertIn("x \\\\_ y", out)
        # The repaired string must parse and preserve the intended characters.
        self.assertEqual(json.loads(out)["a"], "x \\_ y")

    def test_invalid_unicode_escape_not_mangled(self):
        # \u02Z is not a valid hex escape; it becomes a literal backslash + "u02Z".
        out = analyze_repos.repair_invalid_json_escapes('{"a":"\\u02Z"}')
        parsed = json.loads(out)["a"]
        self.assertEqual(parsed, "\\u02Z")


class ExtractionTests(unittest.TestCase):
    def test_strip_basic_fence(self):
        self.assertEqual(
            analyze_repos.strip_code_fences('```json\n{"a":1}\n```'),
            '{"a":1}',
        )

    def test_strip_open_and_closing_fences(self):
        self.assertEqual(
            analyze_repos.strip_code_fences('```\n{"a":1}\n```'),
            '{"a":1}',
        )

    def test_balanced_extraction_respects_strings(self):
        # The closing brace inside a string must not end the extraction early.
        raw = 'x {"a":"has } close brace","b":[1,2]} y'
        self.assertEqual(
            analyze_repos.extract_json_candidate(raw),
            '{"a":"has } close brace","b":[1,2]}',
        )

    def test_balanced_extraction_respects_escaped_quotes(self):
        raw = 'x {"a":"say \\"}\\""} y'
        self.assertEqual(
            analyze_repos.extract_json_candidate(raw),
            '{"a":"say \\"}\\""}',
        )


class RepositoryIsolationTests(unittest.TestCase):
    def test_invalid_repo_does_not_stop_subsequent_repos(self):
        repo_a = {
            "rank": 1,
            "name": "owner/repo-a",
            "reason": "first",
            "why_interesting_today": "a",
        }
        repo_b = {
            "rank": 2,
            "name": "owner/repo-b",
            "reason": "second",
            "why_interesting_today": "b",
        }
        repo_c = {
            "rank": 3,
            "name": "owner/repo-c",
            "reason": "third",
            "why_interesting_today": "c",
        }

        responses = [
            gemini_response('{"name":"owner/repo-a","headline_hook":"ok a"}'),
            # repo-b first try is unparseable (truncated JSON).
            gemini_response('{"name":"owner/repo-b","headline_hook":"trunc'),
            # repo-b retry is still invalid (completely unparseable).
            gemini_response("Not JSON at all."),
            gemini_response('{"name":"owner/repo-c","headline_hook":"ok c"}'),
        ]

        with mock.patch.object(analyze_repos, "call_gemini", side_effect=responses), mock.patch.object(
            analyze_repos, "fetch_readme", return_value="README"
        ):
            results = [analyze_repos.analyze_repository(repo) for repo in (repo_a, repo_b, repo_c)]

        self.assertEqual(results[0]["deep_analysis"]["headline_hook"], "ok a")
        self.assertEqual(results[2]["deep_analysis"]["headline_hook"], "ok c")

        # repo-b is degraded, keeps the schema, and does not carry invented info.
        degraded = results[1]["deep_analysis"]
        self.assertEqual(degraded.get("analysis_status"), "degraded")
        self.assertEqual(degraded["name"], "owner/repo-b")
        self.assertEqual(degraded["headline_hook"], "")
        self.assertEqual(degraded["key_features"], [])

    def test_fallback_analysis_matches_schema(self):
        repo = {"name": "owner/repo-x"}
        fallback = analyze_repos.build_fallback_analysis(repo)
        for field in (
            "name",
            "headline_hook",
            "core_functionality",
            "target_audience",
            "practical_developer_value",
            "analysis_status",
        ):
            self.assertIn(field, fallback)
        self.assertIsInstance(fallback["key_features"], list)
        self.assertIsInstance(fallback["suggested_use_cases"], list)
        self.assertEqual(fallback["name"], "owner/repo-x")

    def test_gemini_api_error_is_isolated_to_its_repository(self):
        repo = {"rank": 1, "name": "owner/repo-fail"}
        with mock.patch.object(
            analyze_repos, "call_gemini", side_effect=RuntimeError("API down")
        ), mock.patch.object(analyze_repos, "fetch_readme", return_value="README"):
            result = analyze_repos.analyze_repository(repo)
        self.assertEqual(result["deep_analysis"].get("analysis_status"), "degraded")


if __name__ == "__main__":
    unittest.main()