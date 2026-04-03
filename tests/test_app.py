"""Tests for the local Flask UX and routing flow."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from threading import Event
from typing import cast
from unittest.mock import patch

from occams_beard.app import create_app
from occams_beard.execution import (
    next_execution_step_label,
    planned_execution_step_breakdown,
    planned_execution_step_count,
)
from occams_beard.models import DomainExecution
from occams_beard.runner import DiagnosticsRunOptions
from support import build_degraded_partial_result


class AppTests(unittest.TestCase):
    """Validate the split web experience and route handling."""

    def setUp(self) -> None:
        self.sample_result = build_degraded_partial_result()
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

    def test_launcher_presence_endpoints_are_disabled_without_tracker(self) -> None:
        heartbeat_response = self.client.post("/__launcher_presence")
        closing_response = self.client.post("/__launcher_presence/closing")

        self.assertEqual(heartbeat_response.status_code, 404)
        self.assertEqual(closing_response.status_code, 404)

    def test_launcher_presence_metadata_and_routes_are_enabled_when_configured(self) -> None:
        class PresenceTracker:
            def __init__(self) -> None:
                self.heartbeat_count = 0
                self.closing_count = 0

            def record_heartbeat(self) -> None:
                self.heartbeat_count += 1

            def record_page_closing(self) -> None:
                self.closing_count += 1

        tracker = PresenceTracker()

        app = create_app(
            {
                "TESTING": True,
                "RUN_EXECUTOR": lambda options: self.sample_result,
                "LAUNCHER_BROWSER_PRESENCE_TRACKER": tracker,
                "LAUNCHER_BROWSER_PRESENCE_INTERVAL_MS": 4321,
            }
        )
        client = app.test_client()

        index_response = client.get("/")
        self.assertEqual(index_response.status_code, 200)
        text = index_response.get_data(as_text=True)
        self.assertIn('name="occams-browser-presence-heartbeat-url"', text)
        self.assertIn('content="/__launcher_presence"', text)
        self.assertIn('name="occams-browser-presence-closing-url"', text)
        self.assertIn('content="/__launcher_presence/closing"', text)
        self.assertIn('name="occams-browser-presence-interval-ms" content="4321"', text)

        heartbeat_response = client.post("/__launcher_presence")
        closing_response = client.post("/__launcher_presence/closing")

        self.assertEqual(heartbeat_response.status_code, 204)
        self.assertEqual(closing_response.status_code, 204)
        self.assertEqual(tracker.heartbeat_count, 1)
        self.assertEqual(tracker.closing_count, 1)

    def wait_for_run_completion(
        self,
        run_id: str,
        *,
        client=None,
        timeout: float = 2.0,
    ) -> dict[str, object]:
        active_client = client or self.client
        deadline = time.time() + timeout
        last_payload: dict[str, object] | None = None
        while time.time() < deadline:
            response = active_client.get(f"/runs/{run_id}/status")
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertIsInstance(payload, dict)
            assert isinstance(payload, dict)
            last_payload = payload
            if payload["status"] == "completed":
                return payload
            time.sleep(0.01)
        self.fail(f"Run {run_id} did not complete in time. Last payload: {last_payload}")

    def test_index_shows_two_entry_paths(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn("Choose Your Path", text)
        self.assertIn("Check My Device", text)
        self.assertIn("Work With Support", text)
        self.assertIn("Skip to main content", text)

    def test_self_serve_mode_uses_symptom_led_copy_and_collapsed_advanced_settings(self) -> None:
        response = self.client.get("/?mode=self-serve")

        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn("Choose the symptom that feels closest.", text)
        self.assertIn("Internet not working", text)
        self.assertIn("VPN or company resource issue", text)
        self.assertIn("data-self-serve-symptom-form", text)
        self.assertIn("Load Recommended Plan", text)
        self.assertNotIn("Start Device Check", text)

    def test_self_serve_query_selection_renders_no_js_run_form(self) -> None:
        response = self.client.get("/?mode=self-serve&symptom=internet-not-working")

        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn("Review the plan before you run it.", text)
        self.assertIn('type="hidden" name="symptom_id" value="internet-not-working"', text)
        self.assertIn('id="self-serve-plan-step"', text)
        self.assertIn("Support asked me to change this plan", text)
        self.assertIn("Start Device Check", text)

    def test_self_serve_plan_fragment_renders_without_full_page_shell(self) -> None:
        response = self.client.get("/self-serve/plan?mode=self-serve&symptom=internet-not-working")

        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn('id="self-serve-plan-step"', text)
        self.assertIn("Review the plan before you run it.", text)
        self.assertIn("Start Device Check", text)
        self.assertNotIn("Choose Your Path", text)

    def test_guided_support_mode_shows_deeper_plan_controls(self) -> None:
        response = self.client.get("/?mode=support")

        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn("Follow the guided plan your technician asked you to run.", text)
        self.assertIn("Confirm the technician-directed plan", text)
        self.assertIn("Locked by default", text)
        self.assertIn("Review consent and handoff", text)
        self.assertIn("Support gave me a different plan", text)
        self.assertIn("Technician asked me to edit the plan details", text)
        self.assertIn("Run Support-Guided Check", text)
        self.assertNotIn("Choose the symptom that feels closest.", text)

    def test_self_serve_submission_maps_symptom_to_profile(self) -> None:
        response = self.client.post(
            "/run",
            data={
                "mode": "self-serve",
                "symptom_id": "vpn-or-company-resource-issue",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/runs/", response.headers["Location"])
        run_id = response.headers["Location"].rsplit("/", 1)[-1]
        self.wait_for_run_completion(run_id)
        self.assertIsNotNone(self.captured_options)
        assert self.captured_options is not None
        self.assertIsNotNone(self.captured_options.profile)
        assert self.captured_options.profile is not None
        self.assertEqual(self.captured_options.profile.profile_id, "vpn-issue")
        self.assertIn("vpn", self.captured_options.selected_checks)
        self.assertIn("services", self.captured_options.selected_checks)

        results_response = self.client.get(f"/results/{run_id}")
        results_text = results_response.get_data(as_text=True)
        self.assertEqual(results_response.status_code, 200)
        self.assertIn("Continue With Support", results_text)
        self.assertIn("What we know", results_text)
        self.assertIn("Download Support Bundle", results_text)
        self.assertIn(
            "The next best step is to continue with support so they can review a deeper guided plan.",
            results_text,
        )

    def test_support_submission_preserves_selected_profile_and_capture_options(self) -> None:
        response = self.client.post(
            "/run",
            data={
                "mode": "support",
                "profile_id": "internal-service-unreachable",
                "checks": ["network", "routing", "dns", "connectivity", "services", "vpn"],
                "targets": "github.com:443\n10.0.0.10:443",
                "dns_hosts": "github.com",
                "enable_trace": "on",
                "capture_raw_commands": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        run_id = response.headers["Location"].rsplit("/", 1)[-1]
        self.wait_for_run_completion(run_id)
        self.assertIsNotNone(self.captured_options)
        assert self.captured_options is not None
        self.assertIsNotNone(self.captured_options.profile)
        assert self.captured_options.profile is not None
        self.assertEqual(
            self.captured_options.profile.profile_id,
            "internal-service-unreachable",
        )
        self.assertTrue(self.captured_options.enable_trace)
        self.assertTrue(self.captured_options.capture_raw_commands)
        self.assertEqual(
            [(target.host, target.port) for target in self.captured_options.targets],
            [("github.com", 443), ("10.0.0.10", 443)],
        )

    def test_self_serve_requires_symptom_selection(self) -> None:
        response = self.client.post(
            "/run",
            data={
                "mode": "self-serve",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "Choose the option that best matches the problem first.",
            response.get_data(as_text=True),
        )

    def test_support_mode_with_previous_run_shows_bridge_banner(self) -> None:
        first_response = self.client.post(
            "/run",
            data={
                "mode": "self-serve",
                "symptom_id": "apps-sites-not-loading",
            },
        )
        run_id = first_response.headers["Location"].rsplit("/", 1)[-1]
        self.wait_for_run_completion(run_id)

        bridge_response = self.client.get(f"/?mode=support&from_run={run_id}")

        self.assertEqual(bridge_response.status_code, 200)
        text = bridge_response.get_data(as_text=True)
        self.assertIn("You do not need to start from scratch.", text)
        self.assertIn("View Earlier Check My Device Results", text)
        self.assertIn("Switch to Suggested Plan:", text)

    def test_support_mode_shows_profile_catalog_issues_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            broken_profile = os.path.join(tempdir, "broken.toml")
            with open(broken_profile, "w", encoding="utf-8") as handle:
                handle.write("id = [\n")

            with patch.dict(os.environ, {"OCCAMS_BEARD_PROFILE_DIR": tempdir}, clear=False):
                response = self.client.get("/?mode=support")

        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn("Some local profiles were skipped.", text)
        self.assertIn(broken_profile, text)

    def test_run_progress_status_exposes_live_execution_updates(self) -> None:
        release_run = Event()
        progress_observed = Event()

        def progress_executor(
            options: DiagnosticsRunOptions,
            *,
            progress_callback=None,
        ):
            self.captured_options = options
            if progress_callback is not None:
                progress_callback(
                    [
                        DomainExecution(
                            domain="host",
                            label="Host basics",
                            status="passed",
                            selected=True,
                            summary=(
                                "Collected endpoint identity and uptime facts "
                                "as a baseline domain."
                            ),
                        ),
                        DomainExecution(
                            domain="resources",
                            label="Resource snapshot",
                            status="not_run",
                            selected=False,
                            summary="Optional and not selected for this run.",
                        ),
                        DomainExecution(
                            domain="dns",
                            label="DNS checks",
                            status="not_run",
                            selected=True,
                            summary="This domain is currently running.",
                            creates_network_egress=True,
                        ),
                    ],
                    "dns",
                    2,
                    planned_execution_step_count(options),
                    {"host": 1, "dns": 1},
                )
                progress_observed.set()
                release_run.wait(timeout=1.0)
            return self.sample_result

        app = create_app(
            {
                "TESTING": True,
                "RUN_EXECUTOR": progress_executor,
            }
        )
        client = app.test_client()

        response = client.post(
            "/run",
            data={
                "mode": "self-serve",
                "symptom_id": "apps-sites-not-loading",
            },
        )

        self.assertEqual(response.status_code, 302)
        run_id = response.headers["Location"].rsplit("/", 1)[-1]
        self.assertTrue(progress_observed.wait(timeout=1.0))

        status_response = client.get(f"/runs/{run_id}/status")
        self.assertEqual(status_response.status_code, 200)
        payload = status_response.get_json()
        self.assertIsInstance(payload, dict)
        assert isinstance(payload, dict)
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["current_domain_label"], "DNS checks")
        self.assertEqual(payload["completed_count"], 2)
        assert self.captured_options is not None
        self.assertEqual(payload["total_count"], planned_execution_step_count(self.captured_options))
        self.assertEqual(payload["rows"][0]["step_progress_label"], "1/1")
        self.assertEqual(payload["rows"][1]["status_label"], "Optional")
        self.assertEqual(payload["rows"][2]["status_label"], "Running now")
        self.assertEqual(
            payload["current_substep_label"],
            next_execution_step_label(self.captured_options, "dns", 1),
        )
        self.assertIn(cast(str, payload["current_substep_label"]), payload["body"])
        self.assertEqual(
            payload["rows"][2]["step_progress_label"],
            f"1/{planned_execution_step_breakdown(self.captured_options)['dns']}",
        )
        self.assertEqual(
            payload["rows"][2]["summary"],
            f"{next_execution_step_label(self.captured_options, 'dns', 1)}.",
        )
        self.assertEqual(payload["update_notice"], "This page updates automatically.")
        self.assertIn("do not need to refresh", payload["mode_notice"])
        self.assertIn("planned probe steps", payload["progress_text"])

        release_run.set()
        final_payload = self.wait_for_run_completion(run_id, client=client)
        self.assertEqual(final_payload["status"], "completed")

    def test_support_results_render_without_template_crash(self) -> None:
        response = self.client.post(
            "/run",
            data={
                "mode": "support",
                "profile_id": "internal-service-unreachable",
                "checks": ["network", "routing", "dns", "connectivity", "services"],
            },
        )

        self.assertEqual(response.status_code, 302)
        run_id = response.headers["Location"].rsplit("/", 1)[-1]
        self.wait_for_run_completion(run_id)

        results_response = self.client.get(f"/results/{run_id}")
        self.assertEqual(results_response.status_code, 200)
        text = results_response.get_data(as_text=True)
        self.assertIn("Technical findings", text)
        self.assertIn("Check details", text)
        self.assertIn("Download Support Bundle", text)
        self.assertIn("Choose a redaction level", text)

    def test_mode_specific_results_cta_ordering_is_stable(self) -> None:
        self_serve_response = self.client.post(
            "/run",
            data={
                "mode": "self-serve",
                "symptom_id": "internet-not-working",
            },
        )
        self.assertEqual(self_serve_response.status_code, 302)
        self_serve_run_id = self_serve_response.headers["Location"].rsplit("/", 1)[-1]
        self.wait_for_run_completion(self_serve_run_id)
        self_serve_results = self.client.get(f"/results/{self_serve_run_id}").get_data(as_text=True)

        self.assertLess(
            self_serve_results.index('data-results-action="continue-support"'),
            self_serve_results.index('data-results-action="rerun"'),
        )

        support_response = self.client.post(
            "/run",
            data={
                "mode": "support",
                "profile_id": "internal-service-unreachable",
            },
        )
        self.assertEqual(support_response.status_code, 302)
        support_run_id = support_response.headers["Location"].rsplit("/", 1)[-1]
        self.wait_for_run_completion(support_run_id)
        support_results = self.client.get(f"/results/{support_run_id}").get_data(as_text=True)

        self.assertNotIn('data-results-action="continue-support"', support_results)
        self.assertLess(
            support_results.index('data-results-action="download-support-bundle"'),
            support_results.index('data-results-action="download-json"'),
        )

    def test_support_results_make_primary_handoff_prominent(self) -> None:
        response = self.client.post(
            "/run",
            data={
                "mode": "support",
                "profile_id": "internal-service-unreachable",
            },
        )

        self.assertEqual(response.status_code, 302)
        run_id = response.headers["Location"].rsplit("/", 1)[-1]
        self.wait_for_run_completion(run_id)

        text = self.client.get(f"/results/{run_id}").get_data(as_text=True)
        self.assertLess(text.index("Primary Handoff"), text.index("Technical Review"))
        self.assertIn("Raw command capture available", text)
        self.assertIn("Choose a redaction level", text)


if __name__ == "__main__":
    unittest.main()
