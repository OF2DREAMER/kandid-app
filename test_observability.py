"""
Unit tests for Kindid Privacy-First Observability Foundation.
Covers:
- GET /api/public/config endpoint security and response shape
- Backend operational event logging and PII/credential scrubbing
- Fail-safe resilience of server and frontend telemetry
- Frontend observability.js sanitization, allowlists, and session recording status
"""

import json
import os
import subprocess
import unittest
from io import BytesIO
from unittest.mock import patch

import server


class TestObservabilityBackend(unittest.TestCase):
    def setUp(self):
        self.handler = server.KandidHandler.__new__(server.KandidHandler)
        self.handler.headers = {}
        self.handler.wfile = BytesIO()
        self.sent_status = []
        self.sent_headers = {}

        def fake_send_response(code):
            self.sent_status.append(code)

        def fake_send_header(name, val):
            self.sent_headers[name.lower()] = val

        def fake_end_headers():
            pass

        self.handler.send_response = fake_send_response
        self.handler.send_header = fake_send_header
        self.handler.end_headers = fake_end_headers

    def test_public_config_endpoint_shape_and_security(self):
        """Verify /api/public/config returns environment flags without leaking secrets."""
        self.handler.path = "/api/public/config"
        self.handler.do_GET()

        self.assertEqual(self.sent_status, [200])
        body_bytes = self.handler.wfile.getvalue()
        data = json.loads(body_bytes.decode("utf-8"))

        self.assertTrue(data.get("success"))
        self.assertIn("environment", data)
        self.assertIn("version", data)
        self.assertIn("posthog_enabled", data)
        self.assertIn("posthog_host", data)
        self.assertIn("posthog_api_key", data)

        # Ensure no sensitive backend secrets or internal variables leaked
        disallowed_keys = [
            "database_url", "db_password", "jwt_secret", "secret_key",
            "razorpay_key_secret", "admin_password", "smtp_password"
        ]
        for key in disallowed_keys:
            self.assertNotIn(key, data)

    def test_log_operational_event_redaction(self):
        """Verify server.log_operational_event completely strips credentials and sensitive fields."""
        with patch("builtins.print") as mock_print:
            unsafe_props = {
                "safe_status": 200,
                "circle": "campus",
                "password": "SuperSecretPassword123",
                "token": "tok_abcdef1234567890",
                "auth_header": "Bearer secret_jwt_token",
                "user_email": "student@example.edu",
                "phone": "+1234567890",
                "raw_gps": "37.7749,-122.4194",
                "nested_dict": {"inner_key": "val"}
            }

            server.log_operational_event("test_security_event", category="auth", properties=unsafe_props)

            mock_print.assert_called_once()
            log_msg = mock_print.call_args[0][0]
            self.assertTrue(log_msg.startswith("[TELEMETRY] "))
            log_data = json.loads(log_msg.replace("[TELEMETRY] ", ""))

            self.assertEqual(log_data["event"], "test_security_event")
            self.assertEqual(log_data["category"], "auth")
            data = log_data["data"]

            # Safe fields retained
            self.assertEqual(data["safe_status"], 200)
            self.assertEqual(data["circle"], "campus")

            # Sensitive fields stripped
            self.assertNotIn("password", data)
            self.assertNotIn("token", data)
            self.assertNotIn("auth_header", data)
            self.assertNotIn("user_email", data)
            self.assertNotIn("phone", data)
            self.assertNotIn("raw_gps", data)
            self.assertNotIn("nested_dict", data)

    def test_log_operational_event_failsafe(self):
        """Telemetry logger must never raise exceptions on malformed input."""
        try:
            server.log_operational_event(None, None)
            server.log_operational_event("bad_event", category="bad", properties="not_a_dict")
            server.log_operational_event(12345, category=None, properties={"valid": True})
        except Exception as e:
            self.fail(f"log_operational_event raised unexpected exception: {e}")


class TestObservabilityFrontend(unittest.TestCase):
    def test_frontend_observability_suite_via_node(self):
        """Execute node unit tests against observability.js to verify privacy allowlists and redaction."""
        repo_dir = os.path.dirname(os.path.abspath(__file__))
        obs_path = os.path.join(repo_dir, "observability.js")
        self.assertTrue(os.path.exists(obs_path), "observability.js must exist on disk")

        node_script = """
        const assert = require('assert');
        const fs = require('fs');
        const vm = require('vm');

        // Setup DOM-like sandbox
        const sandbox = {
            console: console,
            fetch: () => Promise.resolve()
        };
        sandbox.window = sandbox;
        sandbox.location = { hostname: 'localhost' };

        const code = fs.readFileSync('observability.js', 'utf8');
        vm.createContext(sandbox);
        vm.runInContext(code, sandbox);

        const obs = sandbox.KandidObservability;
        assert(obs, 'KandidObservability must be defined');

        // 1. Session recording is hard-disabled
        const config = obs.getConfig();
        assert.strictEqual(config.sessionRecordingEnabled, false, 'Session recording must be false');

        // 2. Allowlist enforcement: only explicitly declared properties allowed
        const rawFeedProps = {
            circle: 'campus',
            count: 10,
            unauthorized_key: 'malicious_data',
            user_token: 'secret_123',
            caption: 'my secret caption',
            message: 'private chat text',
            location: '37.7749,-122.4194'
        };
        const safeFeedProps = obs._sanitizeProperties('feed_loaded', rawFeedProps);
        assert.strictEqual(safeFeedProps.circle, 'campus');
        assert.strictEqual(safeFeedProps.count, 10);
        assert.strictEqual(safeFeedProps.unauthorized_key, undefined, 'Unauthorized key must be stripped');
        assert.strictEqual(safeFeedProps.user_token, undefined, 'Tokens must be stripped');
        assert.strictEqual(safeFeedProps.caption, undefined, 'Captions must be stripped');
        assert.strictEqual(safeFeedProps.message, undefined, 'Messages must be stripped');

        // 3. Sensitive values in string properties are redacted
        const rawLoginProps = {
            method: 'user@example.com', // sensitive email format
            error_category: 'bearer abcdef1234567890abcdef1234567890'
        };
        const safeLoginProps = obs._sanitizeProperties('login_failed', rawLoginProps);
        assert.strictEqual(safeLoginProps.method, '[REDACTED]', 'Email pattern in value must be redacted');
        assert.strictEqual(safeLoginProps.error_category, '[REDACTED]', 'Bearer token in value must be redacted');

        // 4. API telemetry normalizer masks dynamic IDs
        const norm1 = obs._normalizeEndpoint('/api/moment/m_98765/i-was-there?query=123#ref');
        assert.strictEqual(norm1, '/api/moment/:id/i-was-there', 'Dynamic moment ID must be normalized');

        const norm2 = obs._normalizeEndpoint('/api/cluster/c_alpha_beta');
        assert.strictEqual(norm2, '/api/cluster/:id', 'Dynamic cluster ID must be normalized');

        // 5. Fail-safe execution
        obs.captureEvent('unknown_event_xyz', { anything: 1 });
        obs.captureEvent(null, null);
        obs.captureError(null);
        obs.captureApiMetric(null);

        console.log('FRONTEND_OBSERVABILITY_TESTS_PASSED');
        """

        res = subprocess.run(
            ["node", "-e", node_script],
            cwd=repo_dir,
            capture_output=True,
            text=True
        )
        self.assertEqual(res.returncode, 0, f"Node tests failed: {res.stderr}\n{res.stdout}")
        self.assertIn("FRONTEND_OBSERVABILITY_TESTS_PASSED", res.stdout)


if __name__ == "__main__":
    unittest.main()
