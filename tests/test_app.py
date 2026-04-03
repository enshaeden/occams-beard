"""Tests for the local Flask operator interface."""

from __future__ import annotations

import unittest

from occams_beard.app import create_app
from occams_beard.runner import DiagnosticsRunOptions
from support import build_sample_result


class AppTests(unittest.TestCase):
    """Validate Flask routes, form handling, and JSON export."""

    def setUp(self) -> None:
        self.sample_result = build_sample_result()
        self.captured_options: DiagnosticsRunOptions | None = None

        def fake_executor(options: DiagnosticsRunOptions):
            self.captured_options = options
            return self.sample_result

        self.app = create_app(
            {
                "TESTING": True,
                "RUN_EXECUTOR": fake_executor,
            }
        )
        self.client = self.app.test_client()

    def test_index_renders_prefilled_form(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn("Occam's Beard", text)
        self.assertIn("Run Diagnostics", text)
        self.assertIn("github.com:443", text)
        self.assertIn("python.org", text)

    def test_run_submission_redirects_to_results_and_passes_options(self) -> None:
        response = self.client.post(
            "/run",
            data={
                "checks": ["dns", "connectivity"],
                "targets": "github.com:443\n1.1.1.1:53",
                "dns_hosts": "github.com\npython.org",
                "enable_ping": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(self.captured_options)
        assert self.captured_options is not None
        self.assertEqual(self.captured_options.selected_checks, ["dns", "connectivity"])
        self.assertEqual(
            [(target.host, target.port) for target in self.captured_options.targets],
            [("github.com", 443), ("1.1.1.1", 53)],
        )
        self.assertEqual(self.captured_options.dns_hosts, ["github.com", "python.org"])
        self.assertTrue(self.captured_options.enable_ping)
        self.assertFalse(self.captured_options.enable_trace)

        results_response = self.client.get(response.headers["Location"])
        results_text = results_response.get_data(as_text=True)
        self.assertEqual(results_response.status_code, 200)
        self.assertIn("Generic reachability works but a configured service fails", results_text)
        self.assertIn("Download JSON", results_text)

    def test_json_download_returns_serialized_artifact(self) -> None:
        response = self.client.post(
            "/run",
            data={
                "checks": ["dns"],
                "targets": "github.com:443",
                "dns_hosts": "github.com",
            },
        )
        location = response.headers["Location"]

        json_response = self.client.get(f"{location}/result.json")

        self.assertEqual(json_response.status_code, 200)
        self.assertEqual(json_response.mimetype, "application/json")
        self.assertIn('"project_name": "occams-beard"', json_response.get_data(as_text=True))

    def test_invalid_form_input_returns_error_on_index(self) -> None:
        def failing_builder(**_: object):
            raise ValueError("Target must use host:port format: invalid-target")

        app = create_app(
            {
                "TESTING": True,
                "RUN_OPTIONS_FACTORY": failing_builder,
                "RUN_EXECUTOR": lambda _: self.sample_result,
            }
        )
        client = app.test_client()

        response = client.post(
            "/run",
            data={
                "targets": "invalid-target",
                "dns_hosts": "github.com",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Target must use host:port format: invalid-target", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
