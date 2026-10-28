#!/usr/bin/env python3
"""Focused regression coverage for ambient-audio delivery on Safari/WebKit.

Two root causes are covered here:

1. CSP: `<audio>`/`new Audio(...)` is governed by `media-src`, which had no
   directive of its own and therefore fell back to `default-src 'self'`. That
   blocked the `data:` clip produced at review time and the Cloudinary-hosted
   clip used by the feed.
2. Empty captures: `data:audio/mp4;base64,` (a recorder that produced no
   samples) used to be persisted as a zero-byte upload.

Run: python3 test_ambient_audio_csp.py
"""

import base64
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import server


class TestAmbientAudioCsp(unittest.TestCase):
    def _csp(self):
        handler = server.KandidHandler.__new__(server.KandidHandler)
        handler.headers = {}
        handler.request_version = "HTTP/1.1"
        handler.path = "/"
        handler._headers_buffer = []
        handler.wfile = io.BytesIO()
        sent = {}

        def fake_send_response(code, message=None):
            pass

        def fake_send_header(name, val):
            sent[name.lower()] = val

        handler.send_response = fake_send_response
        handler.send_header = fake_send_header
        server.KandidHandler.end_headers(handler)
        return sent.get("content-security-policy", "")

    @staticmethod
    def _directive(csp, name):
        for part in csp.split(";"):
            part = part.strip()
            if part.startswith(name + " "):
                return part[len(name) + 1:].strip()
        return ""

    def test_media_src_directive_exists(self):
        csp = self._csp()
        self.assertTrue(csp, "Content-Security-Policy header missing")
        media = self._directive(csp, "media-src")
        self.assertTrue(media, "media-src directive missing: data: audio falls back to default-src 'self' and is blocked")

    def test_media_src_allows_review_clip_and_cloudinary_feed(self):
        media = self._directive(self._csp(), "media-src").split()
        self.assertIn("'self'", media)                       # /uploads/ fallback audio
        self.assertIn("data:", media)                        # review playback of the captured clip
        self.assertIn("https://res.cloudinary.com", media)   # published feed audio
        self.assertNotIn("*", media, "media-src must not be a wildcard")

    def test_only_media_src_is_relaxed(self):
        csp = self._csp()
        script = self._directive(csp, "script-src")
        connect = self._directive(csp, "connect-src")
        default = self._directive(csp, "default-src")
        self.assertNotIn("data:", script)
        self.assertNotIn("blob:", script)
        self.assertNotIn("data:", connect)
        self.assertNotIn("blob:", connect)
        self.assertEqual(default.strip(), "'self'")
        self.assertIn("object-src 'none'", csp)

    def test_media_src_is_https_only(self):
        media = self._directive(self._csp(), "media-src")
        self.assertNotIn("http://", media)
        self.assertNotIn("javascript:", media)


class TestBackendAudioValidation(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="kindid_audio_")
        self.patches = [
            patch.object(server, "STATIC_DIR", self.tmpdir),
            patch.object(server, "CLOUDINARY_URL", ""),
            patch.object(server, "CLOUDINARY_CLOUD_NAME", ""),
            patch.object(server, "CLOUDINARY_API_KEY", ""),
            patch.object(server, "CLOUDINARY_API_SECRET", ""),
            patch.object(server, "upload_to_cloudinary", lambda *a, **k: ""),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _uploads(self):
        upload_dir = os.path.join(self.tmpdir, "uploads")
        if not os.path.isdir(upload_dir):
            return []
        return sorted(os.listdir(upload_dir))

    def test_recorder_mp4_data_url_is_accepted(self):
        payload = base64.b64encode(b"\x00\x00\x00\x18ftypmp42" + b"\x11" * 32).decode()
        url = server.save_base64_audio("data:audio/mp4;base64," + payload, "ambient")
        self.assertTrue(url.startswith("/uploads/ambient_"), url)
        self.assertTrue(url.endswith(".m4a"), url)
        saved = self._uploads()
        self.assertEqual(len(saved), 1)
        with open(os.path.join(self.tmpdir, "uploads", saved[0]), "rb") as fh:
            self.assertEqual(len(fh.read()), 44)

    def test_wav_fallback_data_url_is_accepted(self):
        payload = base64.b64encode(b"RIFF" + b"\x00" * 60).decode()
        url = server.save_base64_audio("data:audio/wav;base64," + payload, "ambient")
        self.assertTrue(url.endswith(".wav"), url)

    def test_empty_capture_is_rejected(self):
        self.assertEqual(server.save_base64_audio("data:audio/mp4;base64,", "ambient"), "")
        self.assertEqual(server.save_base64_audio("data:audio/wav;base64,   ", "ambient"), "")
        self.assertEqual(self._uploads(), [], "an empty clip must not create an upload")

    def test_empty_capture_is_rejected_before_cloudinary(self):
        calls = []
        with patch.object(server, "upload_to_cloudinary", lambda *a, **k: calls.append(a) or "https://res.cloudinary.com/x"):
            self.assertEqual(server.save_base64_audio("data:audio/mp4;base64,", "ambient"), "")
        self.assertEqual(calls, [], "empty audio must not be uploaded")

    def test_non_audio_payloads_are_rejected(self):
        self.assertEqual(server.save_base64_audio("data:text/html;base64,PHNjcmlwdD4=", "ambient"), "")
        self.assertEqual(server.save_base64_audio("javascript:alert(1)", "ambient"), "")
        self.assertEqual(self._uploads(), [])

    def test_existing_upload_paths_pass_through(self):
        self.assertEqual(server.save_base64_audio("/uploads/old.wav", "ambient"), "/uploads/old.wav")
        self.assertEqual(server.save_base64_audio("https://res.cloudinary.com/demo/audio/x.mp3", "ambient"),
                         "https://res.cloudinary.com/demo/audio/x.mp3")


if __name__ == "__main__":
    unittest.main(verbosity=2)
