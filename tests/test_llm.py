"""Unit tests for pipeline/llm.py (Pure standard library unittest)."""

import json
import sys
import unittest
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))
import llm


class TestLLMExtract(unittest.TestCase):
    def test_extract_plain_json(self):
        body = {
            "choices": [{"message": {"content": "Hello Sci-Fi"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        text, usage = llm._extract(json.dumps(body))
        self.assertEqual(text, "Hello Sci-Fi")
        self.assertEqual(usage["total_tokens"], 15)

    def test_extract_sse_stream(self):
        sse = (
            "data: {\"choices\": [{\"delta\": {\"content\": \"星际\"}}]}\n\n"
            "data: {\"choices\": [{\"delta\": {\"content\": \"远航\"}}]}\n\n"
            "data: {\"choices\": [{\"finish_reason\": \"stop\"}], \"usage\": {\"prompt_tokens\": 20, \"completion_tokens\": 4, \"total_tokens\": 24}}\n\n"
            "data: [DONE]\n\n"
        )
        text, usage = llm._extract(sse)
        self.assertEqual(text, "星际远航")
        self.assertEqual(usage["total_tokens"], 24)

    def test_extract_sse_length_truncation(self):
        sse = (
            "data: {\"choices\": [{\"delta\": {\"content\": \"未完\"}}]}\n\n"
            "data: {\"choices\": [{\"finish_reason\": \"length\"}]}\n\n"
            "data: [DONE]\n\n"
        )
        with self.assertRaises(llm.LLMTokenExhaustedError):
            llm._extract(sse)

    def test_extract_sse_reasoning_exhaustion(self):
        sse = (
            "data: {\"choices\": [{\"delta\": {\"reasoning_content\": \"正在深入推理思考...\"}}]}\n\n"
            "data: [DONE]\n\n"
        )
        with self.assertRaises(llm.LLMTokenExhaustedError):
            llm._extract(sse)


if __name__ == "__main__":
    unittest.main()
