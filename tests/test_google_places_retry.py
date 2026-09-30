"""Offline retry/error-handling tests for the Google Places provider."""

from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from location_intelligence.models import CandidateCategory, SearchRequest
from location_intelligence.providers import GooglePlacesProvider, ProviderError

REQUEST = SearchRequest(13.7652, 100.6431, 1000, CandidateCategory("coffee", ("cafe",), ("coffee",)), max_results=20)
SECRET = "test-secret-key-123"


class _Response:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


def _http_error(code: int) -> HTTPError:
    return HTTPError("https://places.example", code, "err", {}, io.BytesIO(b'{"error": "body with details"}'))


class GooglePlacesRetryTests(unittest.TestCase):
    def provider(self, sleeps: list[float]) -> GooglePlacesProvider:
        return GooglePlacesProvider(SECRET, sleep=sleeps.append)

    def test_retries_rate_limit_and_server_errors_then_succeeds(self):
        sleeps: list[float] = []
        effects = [_http_error(429), _http_error(503), _Response(b'{"places": [{"id": "a"}, "junk"]}')]
        with patch("location_intelligence.providers.urlopen", side_effect=effects) as mocked:
            rows = self.provider(sleeps).search(REQUEST)
        self.assertEqual(rows, [{"id": "a"}])
        self.assertEqual(mocked.call_count, 3)
        self.assertEqual(sleeps, [1.0, 2.0])

    def test_client_error_fails_fast_without_leaking_key_or_body(self):
        sleeps: list[float] = []
        with patch("location_intelligence.providers.urlopen", side_effect=_http_error(403)) as mocked:
            with self.assertRaises(ProviderError) as ctx:
                self.provider(sleeps).search(REQUEST)
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(sleeps, [])
        message = str(ctx.exception)
        self.assertIn("HTTP 403", message)
        self.assertNotIn(SECRET, message)
        self.assertNotIn("body with details", message)

    def test_network_errors_are_bounded(self):
        sleeps: list[float] = []
        with patch("location_intelligence.providers.urlopen", side_effect=URLError("down")) as mocked:
            with self.assertRaises(ProviderError):
                self.provider(sleeps).search(REQUEST)
        self.assertEqual(mocked.call_count, 3)
        self.assertEqual(sleeps, [1.0, 2.0])

    def test_malformed_payloads_raise_provider_error(self):
        for body in (b"not json", b"[1, 2]", b'{"places": {"id": "x"}}'):
            with patch("location_intelligence.providers.urlopen", return_value=_Response(body)):
                with self.assertRaises(ProviderError):
                    self.provider([]).search(REQUEST)

    def test_repr_does_not_expose_key(self):
        self.assertNotIn(SECRET, repr(GooglePlacesProvider(SECRET)))


if __name__ == "__main__":
    unittest.main()
