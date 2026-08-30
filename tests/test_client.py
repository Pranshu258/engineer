import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from ollama_agent.client import OllamaClient, OllamaError


class FakeResponse:
    def __init__(self, chunks):
        self.chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def __iter__(self):
        return iter(self.chunks)


def ndjson(*chunks):
    return [(json.dumps(chunk) + "\n").encode() for chunk in chunks]


class ClientTests(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_streams_text_and_assembles_indexed_tool_calls(self, urlopen):
        urlopen.return_value = FakeResponse(
            ndjson(
                {"message": {"role": "assistant", "content": "hel"}, "done": False},
                {"message": {"role": "assistant", "content": "lo"}, "done": False},
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "type": "function",
                                "function": {
                                    "index": 1,
                                    "name": "list_files",
                                    "arguments": {"path": "."},
                                },
                            },
                            {
                                "type": "function",
                                "function": {
                                    "index": 0,
                                    "name": "read_file",
                                    "arguments": {"path": "a.txt"},
                                },
                            },
                        ],
                    },
                    "done": False,
                },
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "type": "function",
                                "function": {
                                    "index": 1,
                                    "arguments": {"extra": True},
                                },
                            }
                        ],
                    },
                    "done": False,
                },
                {"message": {"role": "assistant", "content": ""}, "done": True},
            )
        )
        streamed = []

        message = OllamaClient("localhost:11434").chat(
            "model", [{"role": "user", "content": "hi"}], [], streamed.append
        )

        self.assertEqual(streamed, ["hel", "lo"])
        self.assertEqual(message["content"], "hello")
        self.assertEqual(
            [call["function"]["name"] for call in message["tool_calls"]],
            ["read_file", "list_files"],
        )
        self.assertEqual(
            message["tool_calls"][1]["function"]["arguments"],
            {"path": ".", "extra": True},
        )
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://localhost:11434/api/chat")
        self.assertTrue(json.loads(request.data)["stream"])

    @patch("urllib.request.urlopen")
    def test_network_error_is_clear(self, urlopen):
        urlopen.side_effect = urllib.error.URLError("refused")
        with self.assertRaisesRegex(OllamaError, "ollama serve"):
            OllamaClient("http://localhost:11434").chat("model", [], [])

    @patch("urllib.request.urlopen")
    def test_http_model_error_is_clear(self, urlopen):
        urlopen.side_effect = urllib.error.HTTPError(
            "url", 404, "not found", {}, io.BytesIO(b'{"error":"model missing"}')
        )
        with self.assertRaisesRegex(OllamaError, "model missing"):
            OllamaClient("http://localhost:11434").chat("absent", [], [])

    @patch("urllib.request.urlopen")
    def test_malformed_stream_is_clear(self, urlopen):
        urlopen.return_value = FakeResponse([b"{bad\n"])
        with self.assertRaisesRegex(OllamaError, "malformed streaming JSON"):
            OllamaClient("http://localhost:11434").chat("model", [], [])

    def test_non_http_endpoint_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "HTTP"):
            OllamaClient("file:///tmp/ollama")

    def test_non_local_endpoint_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "loopback"):
            OllamaClient("https://ollama.example.com")


if __name__ == "__main__":
    unittest.main()
