"""Optional browser-level UI tests for the local diagnostics web app."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
import urllib.response
from threading import Event, Thread
from typing import Any

from werkzeug.serving import make_server

from occams_beard.app import create_app
from occams_beard.models import DomainExecution
from occams_beard.runner import DiagnosticsRunOptions
from support import build_degraded_partial_result


def _browser_tests_enabled() -> bool:
    return os.environ.get("OCCAMS_BEARD_BROWSER_TESTS") == "1"


@unittest.skipUnless(_browser_tests_enabled(), "Browser UI tests are opt-in.")
@unittest.skipUnless(shutil.which("safaridriver"), "safaridriver is required.")
class BrowserUiTests(unittest.TestCase):
    """Validate keyboard flow, details behavior, and CTA ordering in a real browser."""

    app: Any
    server: _ServerThread
    base_url: str
    driver: _SafariDriver

    @classmethod
    def setUpClass(cls) -> None:
        sample_result = build_degraded_partial_result()

        def fake_executor(options: DiagnosticsRunOptions):
            return sample_result

        cls.app = create_app(
            {
                "TESTING": True,
                "RUN_EXECUTOR": fake_executor,
            }
        )
        cls.server = _ServerThread(cls.app)
        cls.server.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.port}"

        cls.driver = _SafariDriver()
        try:
            cls.driver.start()
        except Exception as exc:
            cls.server.stop()
            raise unittest.SkipTest(
                f"Safari WebDriver could not start on this host: {exc}"
            ) from exc

    @classmethod
    def tearDownClass(cls) -> None:
        cls.driver.stop()
        cls.server.stop()

    def test_keyboard_flow_can_open_self_serve_path(self) -> None:
        self.driver.navigate(f"{self.base_url}/")
        self.driver.execute(
            """
            document.body.tabIndex = -1;
            document.body.focus();
            return true;
            """
        )

        active = None
        for _ in range(6):
            self.driver.send_key("\ue004")
            time.sleep(0.1)
            active = self.driver.execute(
                """
                if (!document.activeElement) {
                  return null;
                }
                return {
                  modeLink: document.activeElement.dataset.modeLink || null,
                  text: (document.activeElement.textContent || "").trim(),
                };
                """
            )
            if active and active.get("modeLink") == "self-serve":
                break

        self.assertIsNotNone(active)
        assert active is not None
        self.assertEqual(active.get("modeLink"), "self-serve")

        self.driver.send_key("\ue007")
        self.driver.wait_until(lambda: "mode=self-serve" in self.driver.current_url())
        heading = self.driver.execute(
            "return document.querySelector('.experience-card h2').textContent.trim();"
        )
        self.assertEqual(heading, "Choose the issue you want to check.")

        self.driver.execute(
            """
            const input = document.querySelector('[data-symptom-choice="internet-not-working"]');
            input.checked = true;
            input.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
            """
        )
        self.driver.wait_until(
            lambda: "symptom=internet-not-working" in self.driver.current_url()
        )
        self.driver.wait_until(
            lambda: "#self-serve-plan-step" in self.driver.current_url()
        )
        self.driver.wait_until(
            lambda: self.driver.execute(
                """
                const plan = document.querySelector('#self-serve-plan-step');
                if (!plan) {
                  return false;
                }
                const rect = plan.getBoundingClientRect();
                return rect.top >= -40 && rect.top <= Math.max(window.innerHeight * 0.25, 160);
                """
            )
            is True
        )
        self.assertEqual(
            self.driver.execute(
                "return document.querySelector('[data-self-serve-plan-summary] .mode-chip').textContent.trim();"
            ),
            "Recommended plan",
        )

    def test_details_toggle_and_mode_specific_cta_ordering(self) -> None:
        self.driver.navigate(f"{self.base_url}/?mode=support")
        self.driver.wait_until(
            lambda: self.driver.execute("return document.readyState;") == "complete"
        )
        self.assertEqual(
            self.driver.execute(
                "return document.querySelector('[data-support-plan-summary] h2').textContent.trim();"
            ),
            "Confirm the technician-directed plan",
        )
        self.assertFalse(
            self.driver.execute(
                "return document.querySelector('[data-support-plan-picker]').open;"
            )
        )
        self.assertFalse(
            self.driver.execute(
                "return document.querySelector('[data-support-plan-edit]').open;"
            )
        )

        self_serve_run_id = self._start_run(
            {
                "mode": "self-serve",
                "symptom_id": "internet-not-working",
            }
        )
        self.driver.navigate(f"{self.base_url}/results/{self_serve_run_id}")
        self.driver.wait_until(
            lambda: self.driver.execute("return document.readyState;") == "complete"
        )

        self.assertFalse(
            self.driver.execute(
                "return document.querySelector('[data-results-details=\"check-details\"]').open;"
            )
        )
        self.driver.click('[data-results-details="check-details"] summary')
        self.driver.wait_until(
            lambda: self.driver.execute(
                "return document.querySelector('[data-results-details=\"check-details\"]').open;"
            )
            is True
        )

        self_serve_actions = self.driver.execute(
            """
            return Array.from(
              document.querySelectorAll('[data-results-hero-actions] [data-results-action]')
            ).map((element) => element.getAttribute('data-results-action'));
            """
        )
        self.assertEqual(self_serve_actions[:2], ["continue-support", "rerun"])

        support_run_id = self._start_run(
            {
                "mode": "support",
                "profile_id": "internal-service-unreachable",
            }
        )
        self.driver.navigate(f"{self.base_url}/results/{support_run_id}")
        self.driver.wait_until(
            lambda: self.driver.execute("return document.readyState;") == "complete"
        )

        support_actions = self.driver.execute(
            """
            return Array.from(
              document.querySelectorAll('[data-results-hero-actions] [data-results-action]')
            ).map((element) => element.getAttribute('data-results-action'));
            """
        )
        export_actions = self.driver.execute(
            """
            return Array.from(
              document.querySelectorAll('[data-results-export-actions] [data-results-action]')
            ).map((element) => element.getAttribute('data-results-action'));
            """
        )
        self.assertEqual(support_actions, ["rerun"])
        self.assertEqual(export_actions, ["download-support-bundle", "download-json"])

    def test_multi_target_progress_page_shows_domain_subcounts(self) -> None:
        release_run = Event()
        progress_observed = Event()
        sample_result = build_degraded_partial_result()

        def progress_executor(
            options: DiagnosticsRunOptions,
            *,
            progress_callback=None,
        ):
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
                            domain="connectivity",
                            label="Generic connectivity",
                            status="not_run",
                            selected=True,
                            summary="This domain is currently running.",
                            creates_network_egress=True,
                        ),
                    ],
                    "connectivity",
                    2,
                    7,
                    {"host": 1, "connectivity": 1},
                )
                progress_observed.set()
                release_run.wait(timeout=1.0)
            return sample_result

        app = create_app(
            {
                "TESTING": True,
                "RUN_EXECUTOR": progress_executor,
            }
        )
        server = _ServerThread(app)
        server.start()
        try:
            response = _request(
                f"http://127.0.0.1:{server.port}/run",
                method="POST",
                data={
                    "mode": "support",
                    "profile_id": "internal-service-unreachable",
                    "checks": ["connectivity"],
                    "targets": "github.com:443\n1.1.1.1:53",
                    "enable_ping": "on",
                    "enable_trace": "on",
                },
                follow_redirects=False,
            )
            self.assertEqual(response.status, 302)
            run_id = response.headers["Location"].rsplit("/", 1)[-1]
            self.assertTrue(progress_observed.wait(timeout=1.0))

            self.driver.navigate(f"http://127.0.0.1:{server.port}/runs/{run_id}")
            self.driver.wait_until(
                lambda: self.driver.execute("return document.readyState;") == "complete"
            )
            self.driver.wait_until(
                lambda: self.driver.execute(
                    """
                    const rows = Array.from(document.querySelectorAll('[data-progress-rows] li'));
                    const connectivity = rows.find((row) => {
                      const title = row.querySelector('strong');
                      return title && title.textContent.trim() === 'Generic connectivity';
                    });
                    if (!connectivity) {
                      return false;
                    }
                    const stepCount = connectivity.querySelector('[data-progress-step-count]');
                    return stepCount && stepCount.textContent.trim() === '1/6';
                    """
                )
                is True
            )

            progress_count = self.driver.execute(
                "return document.querySelector('[data-progress-count]').textContent.trim();"
            )
            connectivity_row = self.driver.execute(
                """
                const rows = Array.from(document.querySelectorAll('[data-progress-rows] li'));
                const connectivity = rows.find((row) => {
                  const title = row.querySelector('strong');
                  return title && title.textContent.trim() === 'Generic connectivity';
                });
                const stepCount = connectivity.querySelector('[data-progress-step-count]');
                const phase = connectivity.querySelector('[data-progress-phase]');
                return {
                  ariaCurrent: connectivity.getAttribute('aria-current'),
                  stepCount: stepCount ? stepCount.textContent.trim() : null,
                  phase: phase ? phase.textContent.trim() : null,
                };
                """
            )

            self.assertEqual(progress_count, "2 of 7")
            self.assertEqual(connectivity_row["ariaCurrent"], "step")
            self.assertEqual(connectivity_row["stepCount"], "1/6")
            self.assertEqual(connectivity_row["phase"], "Running now")
        finally:
            release_run.set()
            server.stop()

    def _start_run(self, data: dict[str, str]) -> str:
        response = _request(
            f"{self.base_url}/run",
            method="POST",
            data=data,
            follow_redirects=False,
        )
        self.assertEqual(response.status, 302)
        location = response.headers["Location"]
        run_id = location.rsplit("/", 1)[-1]

        deadline = time.time() + 3.0
        while time.time() < deadline:
            status_response = _request(f"{self.base_url}/runs/{run_id}/status")
            payload = json.loads(status_response.body)
            if payload["status"] == "completed":
                return run_id
            time.sleep(0.05)

        self.fail(f"Run {run_id} did not complete in time.")


class _ServerThread:
    def __init__(self, app) -> None:
        self._server = make_server("127.0.0.1", 0, app)
        self.port = self._server.server_port
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._thread.join(timeout=2.0)


class _SafariDriver:
    element_key = "element-6066-11e4-a52e-4f735466cecf"

    def __init__(self) -> None:
        self._port = _find_open_port()
        self._process: subprocess.Popen[str] | None = None
        self._session_id: str | None = None

    def start(self) -> None:
        self._process = subprocess.Popen(
            ["safaridriver", "-p", str(self._port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        _wait_for_port(self._port)
        response = self._request(
            "POST",
            "/session",
            {
                "capabilities": {
                    "alwaysMatch": {
                        "browserName": "Safari",
                    }
                }
            },
        )
        value = response.get("value", {})
        self._session_id = value.get("sessionId") or response.get("sessionId")
        if not self._session_id:
            raise RuntimeError("Safari WebDriver did not return a session id.")

    def stop(self) -> None:
        if self._session_id:
            try:
                self._request("DELETE", f"/session/{self._session_id}")
            except Exception:
                pass
        if self._process is not None:
            self._process.terminate()
            self._process.wait(timeout=5.0)

    def navigate(self, url: str) -> None:
        self._request("POST", f"/session/{self._session_id}/url", {"url": url})

    def current_url(self) -> str:
        response = self._request("GET", f"/session/{self._session_id}/url")
        return response["value"]

    def execute(self, script: str, args: list[Any] | None = None) -> Any:
        response = self._request(
            "POST",
            f"/session/{self._session_id}/execute/sync",
            {"script": script, "args": args or []},
        )
        return response["value"]

    def click(self, selector: str) -> None:
        element_id = self._find(selector)
        self._request("POST", f"/session/{self._session_id}/element/{element_id}/click", {})

    def send_key(self, value: str) -> None:
        self._request(
            "POST",
            f"/session/{self._session_id}/actions",
            {
                "actions": [
                    {
                        "type": "key",
                        "id": "keyboard",
                        "actions": [
                            {"type": "keyDown", "value": value},
                            {"type": "keyUp", "value": value},
                        ],
                    }
                ]
            },
        )

    def wait_until(self, predicate, *, timeout: float = 3.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        raise AssertionError("Timed out waiting for browser condition.")

    def _find(self, selector: str) -> str:
        response = self._request(
            "POST",
            f"/session/{self._session_id}/element",
            {"using": "css selector", "value": selector},
        )
        value = response["value"]
        return value[self.element_key]

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            f"http://127.0.0.1:{self._port}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5.0) as response:
            return json.loads(response.read().decode("utf-8"))


class _HttpResponse:
    def __init__(self, status: int, headers: Any, body: str) -> None:
        self.status = status
        self.headers = headers
        self.body = body


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

    def http_error_302(self, req, fp, code, msg, headers):
        return urllib.response.addinfourl(fp, headers, req.full_url, code)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


def _request(
    url: str,
    *,
    method: str = "GET",
    data: dict[str, Any] | None = None,
    follow_redirects: bool = True,
) -> _HttpResponse:
    encoded = None
    headers: dict[str, str] = {}
    if data is not None:
        encoded = urllib.parse.urlencode(data, doseq=True).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    request = urllib.request.Request(url, data=encoded, headers=headers, method=method)
    opener = (
        urllib.request.build_opener()
        if follow_redirects
        else urllib.request.build_opener(_NoRedirect)
    )

    try:
        with opener.open(request, timeout=5.0) as response:
            return _HttpResponse(
                getattr(response, "status", response.getcode()),
                response.headers,
                response.read().decode("utf-8"),
            )
    except urllib.error.HTTPError as exc:
        return _HttpResponse(exc.code, exc.headers, exc.read().decode("utf-8"))


def _find_open_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_port(port: int, *, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.05)
    raise RuntimeError(f"Timed out waiting for port {port}.")
