"""Tests for the shared diagnostics runner."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from occams_beard.defaults import DEFAULT_CHECKS
from occams_beard.execution import planned_execution_step_count
from occams_beard.intake import IntakeContext
from occams_beard.models import (
    ClockSkewCheck,
    ConnectivityState,
    CpuState,
    DiagnosticWarning,
    DnsResolutionCheck,
    DnsState,
    Finding,
    HostBasics,
    MemoryState,
    TcpConnectivityCheck,
    TcpTarget,
    TimeState,
)
from occams_beard.runner import DiagnosticsRunOptions, build_run_options, run_diagnostics


class RunnerTests(unittest.TestCase):
    """Validate shared runner option resolution and execution flow."""

    def test_build_run_options_uses_defaults(self) -> None:
        options = build_run_options()

        self.assertEqual(options.selected_checks, DEFAULT_CHECKS)
        self.assertEqual([target.host for target in options.targets], ["github.com", "1.1.1.1"])
        self.assertEqual(options.dns_hosts, ["github.com", "python.org"])
        self.assertFalse(options.enable_ping)
        self.assertFalse(options.enable_trace)
        self.assertFalse(options.enable_time_skew_check)
        self.assertIsNone(options.profile)

    def test_build_run_options_uses_profile_defaults(self) -> None:
        options = build_run_options(profile_id="dns-issue")

        self.assertEqual(options.profile.profile_id, "dns-issue")
        self.assertEqual(
            options.selected_checks,
            ["time", "network", "routing", "dns", "connectivity"],
        )
        self.assertEqual(options.dns_hosts, ["github.com", "python.org", "pypi.org"])
        self.assertEqual(
            [(target.host, target.port) for target in options.targets],
            [("1.1.1.1", 53), ("8.8.8.8", 53)],
        )

    def test_build_run_options_records_validation_trace_when_intake_context_is_supplied(
        self,
    ) -> None:
        intake_context = IntakeContext(
            selected_symptom_key="apps-sites-not-loading",
            selected_symptom_label="Apps or sites not loading",
            resolved_intent_key="partial_access_or_dns",
            clarification_answers=(("vpn_connected", "no"),),
            scope_rationale="refined_context_supplied",
        )

        options = build_run_options(intake_context=intake_context)

        self.assertIsNotNone(options.intake_context)
        assert options.intake_context is not None
        self.assertEqual(
            options.intake_context.selected_symptom_key,
            intake_context.selected_symptom_key,
        )
        self.assertIn("validation_adjustments", options.intake_context.trace_metadata)
        self.assertIn("decision", options.intake_context.trace_metadata["validation_adjustments"])

    def test_run_diagnostics_returns_result_and_skips_unselected_collectors(self) -> None:
        options = DiagnosticsRunOptions(
            selected_checks=["dns"],
            targets=[TcpTarget(host="github.com", port=443)],
            dns_hosts=["github.com"],
        )
        finding = Finding(
            identifier="dns-degraded",
            severity="medium",
            title="DNS is degraded",
            summary="A hostname failed to resolve.",
            evidence=["github.com failed to resolve."],
            probable_cause="DNS resolution is partially failing.",
            fault_domain="dns",
            confidence=0.88,
        )

        with (
            patch(
                "occams_beard.domain_registry.collect_host_basics",
                return_value=(
                    HostBasics(
                        hostname="demo-host",
                        operating_system="Linux",
                        kernel="6.8.0",
                        current_user="operator",
                        uptime_seconds=120,
                    ),
                    [],
                ),
            ),
            patch(
                "occams_beard.domain_registry.collect_dns_state",
                return_value=(DnsState(), []),
            ),
            patch(
                "occams_beard.result_builder.evaluate_selected_findings",
                return_value=([finding], "dns"),
            ),
            patch("occams_beard.domain_registry.collect_time_state") as mock_time,
            patch("occams_beard.domain_registry.collect_resource_state") as mock_resources,
            patch("occams_beard.domain_registry.collect_storage_state") as mock_storage,
            patch("occams_beard.domain_registry.collect_network_state") as mock_network,
            patch("occams_beard.domain_registry.collect_route_summary") as mock_routes,
            patch("occams_beard.domain_registry.collect_connectivity_state") as mock_connectivity,
            patch("occams_beard.domain_registry.collect_service_state") as mock_services,
            patch("occams_beard.domain_registry.collect_vpn_state") as mock_vpn,
        ):
            result = run_diagnostics(options)

        self.assertEqual(result.metadata.selected_checks, ["dns"])
        self.assertEqual(result.probable_fault_domain, "dns")
        self.assertEqual(result.findings[0].identifier, "dns-degraded")
        self.assertEqual(result.facts.host.hostname, "demo-host")
        self.assertEqual(result.schema_version, "1.4.0")
        self.assertTrue(result.execution)
        self.assertIsNotNone(result.guided_experience)
        mock_time.assert_not_called()
        mock_resources.assert_not_called()
        mock_storage.assert_not_called()
        mock_network.assert_not_called()
        mock_routes.assert_not_called()
        mock_connectivity.assert_not_called()
        mock_services.assert_not_called()
        mock_vpn.assert_not_called()

    def test_run_diagnostics_emits_progress_for_selected_domains(self) -> None:
        options = DiagnosticsRunOptions(
            selected_checks=["dns"],
            targets=[TcpTarget(host="github.com", port=443)],
            dns_hosts=["github.com"],
        )
        progress_updates: list[tuple[list[str], str | None, int, int, dict[str, int]]] = []

        def capture_progress(
            execution,
            active_domain: str | None,
            completed_count: int,
            total_count: int,
            completed_steps_by_domain: dict[str, int],
        ) -> None:
            progress_updates.append(
                (
                    [record.domain for record in execution if record.selected],
                    active_domain,
                    completed_count,
                    total_count,
                    completed_steps_by_domain,
                )
            )

        def fake_collect_dns_state(hostnames, *, progress_callback=None):
            if progress_callback is not None:
                progress_callback(1)
                progress_callback(2)
            return DnsState(resolvers=["1.1.1.1"]), []

        with (
            patch(
                "occams_beard.domain_registry.collect_host_basics",
                return_value=(
                    HostBasics(
                        hostname="demo-host",
                        operating_system="Linux",
                        kernel="6.8.0",
                        current_user="operator",
                        uptime_seconds=120,
                    ),
                    [],
                ),
            ),
            patch(
                "occams_beard.domain_registry.collect_dns_state",
                side_effect=fake_collect_dns_state,
            ),
            patch(
                "occams_beard.result_builder.evaluate_selected_findings",
                return_value=([], "healthy"),
            ),
        ):
            run_diagnostics(
                options,
                progress_callback=capture_progress,
            )

        self.assertEqual(len(progress_updates), 4)
        self.assertEqual(progress_updates[0][0], ["host", "dns"])
        self.assertEqual(progress_updates[0][1], "dns")
        self.assertEqual(progress_updates[0][2:4], (1, 3))
        self.assertEqual(progress_updates[1][1], "dns")
        self.assertEqual(progress_updates[1][2:4], (2, 3))
        self.assertEqual(progress_updates[1][4]["dns"], 1)
        self.assertEqual(progress_updates[2][1], "dns")
        self.assertEqual(progress_updates[2][2:4], (3, 3))

    def test_run_diagnostics_marks_time_domain_partial_when_skew_check_is_inconclusive(
        self,
    ) -> None:
        options = DiagnosticsRunOptions(
            selected_checks=["time"],
            targets=[],
            dns_hosts=[],
            enable_time_skew_check=True,
        )

        with (
            patch(
                "occams_beard.domain_registry.collect_host_basics",
                return_value=(
                    HostBasics(
                        hostname="demo-host",
                        operating_system="Linux",
                        kernel="6.8.0",
                        current_user="operator",
                        uptime_seconds=120,
                    ),
                    [],
                ),
            ),
            patch(
                "occams_beard.domain_registry.collect_time_state",
                return_value=(
                    TimeState(
                        local_time_iso="2026-04-04T09:30:00-07:00",
                        utc_time_iso="2026-04-04T16:30:00+00:00",
                        timezone_name="PDT",
                        timezone_identifier="America/Los_Angeles",
                        timezone_identifier_source="localtime-symlink",
                        utc_offset_minutes=-420,
                        timezone_offset_consistent=True,
                        skew_check=ClockSkewCheck(
                            status="failed",
                            reference_kind="https-date-header",
                            reference_label="GitHub HTTPS response date",
                            reference_url="https://github.com/",
                            error="missing-date-header",
                            duration_ms=120,
                        ),
                    ),
                    [
                        DiagnosticWarning(
                            domain="time",
                            code="clock-skew-check-failed",
                            message=(
                                "The bounded external clock-reference check "
                                "could not confirm skew: missing-date-header."
                            ),
                        )
                    ],
                ),
            ),
            patch(
                "occams_beard.result_builder.evaluate_selected_findings",
                return_value=([], "healthy"),
            ),
        ):
            result = run_diagnostics(options)

        time_record = next(record for record in result.execution if record.domain == "time")
        self.assertEqual(time_record.status, "partial")
        self.assertTrue(time_record.creates_network_egress)
        self.assertEqual(
            [warning.code for warning in time_record.warnings],
            ["clock-skew-check-failed"],
        )

    def test_run_diagnostics_emits_progress_inside_resource_collection(self) -> None:
        options = DiagnosticsRunOptions(
            selected_checks=["resources"],
            targets=[],
            dns_hosts=[],
        )
        progress_updates: list[tuple[str | None, int, int, dict[str, int]]] = []

        def capture_progress(
            _execution,
            active_domain: str | None,
            completed_count: int,
            total_count: int,
            completed_steps_by_domain: dict[str, int],
        ) -> None:
            progress_updates.append(
                (
                    active_domain,
                    completed_count,
                    total_count,
                    completed_steps_by_domain,
                )
            )

        def fake_collect_resource_state(*, progress_callback=None):
            if progress_callback is not None:
                progress_callback(1)
                progress_callback(2)
                progress_callback(3)
            return (
                CpuState(logical_cpus=8),
                MemoryState(total_bytes=1000, available_bytes=500, free_bytes=400),
                None,
                None,
                [],
            )

        with (
            patch(
                "occams_beard.domain_registry.collect_host_basics",
                return_value=(
                    HostBasics(
                        hostname="demo-host",
                        operating_system="Linux",
                        kernel="6.8.0",
                        current_user="operator",
                        uptime_seconds=120,
                    ),
                    [],
                ),
            ),
            patch(
                "occams_beard.domain_registry.collect_resource_state",
                side_effect=fake_collect_resource_state,
            ),
            patch(
                "occams_beard.result_builder.evaluate_selected_findings",
                return_value=([], "healthy"),
            ),
        ):
            run_diagnostics(options, progress_callback=capture_progress)

        self.assertEqual(progress_updates[0][0], "resources")
        self.assertEqual(progress_updates[0][1:3], (1, 4))
        self.assertEqual(progress_updates[1][0], "resources")
        self.assertEqual(progress_updates[1][1:3], (2, 4))
        self.assertEqual(progress_updates[1][3]["resources"], 1)
        self.assertEqual(progress_updates[2][0], "resources")
        self.assertEqual(progress_updates[2][1:3], (3, 4))
        self.assertEqual(progress_updates[2][3]["resources"], 2)
        self.assertEqual(progress_updates[3][0], "resources")
        self.assertEqual(progress_updates[3][1:3], (4, 4))
        self.assertEqual(progress_updates[3][3]["resources"], 3)
        self.assertEqual(progress_updates[4][0], None)

    def test_planned_execution_step_count_grows_with_targets_and_enabled_probes(self) -> None:
        options = DiagnosticsRunOptions(
            selected_checks=["dns", "connectivity", "services"],
            targets=[
                TcpTarget(host="github.com", port=443),
                TcpTarget(host="1.1.1.1", port=53),
            ],
            dns_hosts=["github.com", "python.org", "pypi.org"],
            enable_ping=True,
            enable_trace=True,
        )

        self.assertEqual(planned_execution_step_count(options), 13)

    def test_run_diagnostics_marks_dns_timeout_as_partial_execution(self) -> None:
        options = DiagnosticsRunOptions(
            selected_checks=["dns"],
            targets=[],
            dns_hosts=["github.com"],
        )

        with (
            patch(
                "occams_beard.domain_registry.collect_host_basics",
                return_value=(
                    HostBasics(
                        hostname="demo-host",
                        operating_system="Linux",
                        kernel="6.8.0",
                        current_user="operator",
                        uptime_seconds=120,
                    ),
                    [],
                ),
            ),
            patch(
                "occams_beard.domain_registry.collect_dns_state",
                return_value=(
                    DnsState(
                        resolvers=["1.1.1.1"],
                        checks=[
                            DnsResolutionCheck(
                                hostname="github.com",
                                success=False,
                                error="hostname-resolution-timeout",
                                duration_ms=2000,
                            )
                        ],
                    ),
                    [
                        DiagnosticWarning(
                            domain="dns",
                            code="hostname-resolution-timeout",
                            message="Hostname resolution timed out for github.com.",
                        )
                    ],
                ),
            ),
        ):
            result = run_diagnostics(options)

        dns_execution = next(record for record in result.execution if record.domain == "dns")
        self.assertEqual(dns_execution.status, "partial")
        self.assertEqual(dns_execution.probes[1].status, "partial")
        self.assertEqual(result.findings[0].identifier, "healthy-baseline")

    def test_run_diagnostics_marks_trace_target_resolution_timeout_as_partial_execution(
        self,
    ) -> None:
        options = DiagnosticsRunOptions(
            selected_checks=["connectivity"],
            targets=[TcpTarget(host="github.com", port=443)],
            dns_hosts=[],
            enable_trace=True,
        )

        with (
            patch(
                "occams_beard.domain_registry.collect_host_basics",
                return_value=(
                    HostBasics(
                        hostname="demo-host",
                        operating_system="Linux",
                        kernel="6.8.0",
                        current_user="operator",
                        uptime_seconds=120,
                    ),
                    [],
                ),
            ),
            patch(
                "occams_beard.domain_registry.collect_connectivity_state",
                return_value=(
                    ConnectivityState(
                        internet_reachable=True,
                        tcp_checks=[
                            TcpConnectivityCheck(
                                target=TcpTarget(host="github.com", port=443),
                                success=True,
                                latency_ms=12.5,
                                duration_ms=13,
                            )
                        ],
                    ),
                    [
                        DiagnosticWarning(
                            domain="connectivity",
                            code="trace-target-resolution-timeout",
                            message="Trace target hostname resolution timed out for github.com.",
                        )
                    ],
                ),
            ),
        ):
            result = run_diagnostics(options)

        connectivity_execution = next(
            record for record in result.execution if record.domain == "connectivity"
        )
        self.assertEqual(connectivity_execution.status, "partial")


if __name__ == "__main__":
    unittest.main()
