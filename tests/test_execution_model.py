"""Focused tests for the execution-plan, run-context, and result-assembly model."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from occams_beard.domain_registry import build_execution_plan, iter_registered_domains
from occams_beard.execution import (
    build_execution_records,
    planned_execution_step_breakdown,
    planned_execution_step_count,
)
from occams_beard.models import DiagnosticWarning, StorageDeviceHealth, TcpTarget
from occams_beard.profile_catalog import get_profile
from occams_beard.result_builder import assemble_endpoint_result
from occams_beard.run_context import DiagnosticsRunContext
from occams_beard.runner import DiagnosticsRunOptions
from support import build_default_run_result, build_profile_dns_issue_result


class ExecutionModelTests(unittest.TestCase):
    """Protect the architecture seams around orchestration and result assembly."""

    def test_progress_waits_until_host_completion(self) -> None:
        options = DiagnosticsRunOptions(
            selected_checks=["dns"],
            targets=[],
            dns_hosts=["github.com"],
        )
        progress_updates = []
        context = DiagnosticsRunContext(
            options=options,
            execution_plan=build_execution_plan(options),
            progress_callback=lambda *args: progress_updates.append(args),
        )

        context.record_domain_progress("dns", 1)

        self.assertEqual(progress_updates, [])

        fixture = build_profile_dns_issue_result()
        context.set_host(fixture.facts.host)
        with patch("occams_beard.run_context.time.perf_counter", return_value=12.0):
            context.complete_domain("host", started_at=10.0)

        self.assertEqual(len(progress_updates), 1)
        progress_execution, active_domain, completed_count, total_count, completed_steps = (
            progress_updates[0]
        )
        self.assertEqual(active_domain, "dns")
        self.assertEqual(completed_count, 2)
        self.assertEqual(total_count, 3)
        self.assertEqual(completed_steps["host"], 1)
        self.assertEqual(completed_steps["dns"], 1)
        self.assertEqual(
            [record.domain for record in progress_execution if record.selected],
            ["host", "dns"],
        )

    def test_execution_plan_step_count_supports_minimal_and_multi_domain_runs(self) -> None:
        minimal_options = DiagnosticsRunOptions(
            selected_checks=[],
            targets=[],
            dns_hosts=[],
        )
        multi_domain_options = DiagnosticsRunOptions(
            selected_checks=["dns", "connectivity", "services"],
            targets=[
                TcpTarget(host="github.com", port=443),
                TcpTarget(host="1.1.1.1", port=53),
            ],
            dns_hosts=["github.com", "python.org"],
            enable_ping=True,
        )

        self.assertEqual(planned_execution_step_count(minimal_options), 1)
        self.assertEqual(planned_execution_step_breakdown(minimal_options)["host"], 1)
        self.assertEqual(
            {
                domain: count
                for domain, count in planned_execution_step_breakdown(minimal_options).items()
                if count
            },
            {"host": 1},
        )

        self.assertEqual(planned_execution_step_count(multi_domain_options), 10)
        self.assertEqual(
            planned_execution_step_breakdown(multi_domain_options),
            {
                "host": 1,
                "time": 0,
                "resources": 0,
                "storage": 0,
                "network": 0,
                "routing": 0,
                "dns": 3,
                "connectivity": 4,
                "vpn": 0,
                "services": 2,
            },
        )

    def test_time_domain_adds_optional_skew_probe_step_only_when_enabled(self) -> None:
        local_only_options = DiagnosticsRunOptions(
            selected_checks=["time"],
            targets=[],
            dns_hosts=[],
        )
        skew_options = DiagnosticsRunOptions(
            selected_checks=["time"],
            targets=[],
            dns_hosts=[],
            enable_time_skew_check=True,
        )

        self.assertEqual(planned_execution_step_breakdown(local_only_options)["time"], 1)
        self.assertEqual(planned_execution_step_breakdown(skew_options)["time"], 2)

    def test_complete_domain_tracks_duration_warnings_and_steps(self) -> None:
        options = DiagnosticsRunOptions(
            selected_checks=["dns"],
            targets=[],
            dns_hosts=["github.com"],
        )
        fixture = build_profile_dns_issue_result()
        context = DiagnosticsRunContext(
            options=options,
            execution_plan=build_execution_plan(options),
        )
        context.set_host(fixture.facts.host)
        context.completed_domains.add("host")
        context.completed_steps_by_domain["host"] = 1
        context.set_dns(fixture.facts.dns)

        warning = DiagnosticWarning(
            domain="dns",
            code="resolver-warning",
            message="Resolver inventory is degraded.",
        )
        with patch("occams_beard.run_context.time.perf_counter", return_value=13.5):
            context.complete_domain("dns", started_at=10.0, warnings=[warning])

        self.assertEqual(context.durations_ms["dns"], 3500)
        self.assertEqual(context.warnings, [warning])
        self.assertIn("dns", context.completed_domains)
        self.assertEqual(context.completed_steps_by_domain["dns"], 2)

    def test_result_assembly_uses_completed_run_context(self) -> None:
        fixture = build_profile_dns_issue_result()
        profile = get_profile("dns-issue")
        options = DiagnosticsRunOptions(
            selected_checks=list(profile.recommended_checks),
            targets=list(profile.tcp_targets),
            dns_hosts=list(profile.dns_hosts),
            profile=profile,
        )
        context = DiagnosticsRunContext(
            options=options,
            execution_plan=build_execution_plan(options),
        )
        context.set_host(fixture.facts.host)
        context.set_resources(
            cpu=fixture.facts.resources.cpu,
            memory=fixture.facts.resources.memory,
            battery=fixture.facts.resources.battery,
        )
        context.set_storage(
            disks=fixture.facts.resources.disks,
            storage_devices=fixture.facts.resources.storage_devices,
        )
        context.set_network(fixture.facts.network)
        context.set_route_summary(fixture.facts.network.route_summary)
        context.set_dns(fixture.facts.dns)
        context.set_connectivity(fixture.facts.connectivity)
        context.set_vpn(fixture.facts.vpn)
        context.set_services(fixture.facts.services)
        if fixture.facts.time is not None:
            context.set_time(fixture.facts.time)
        context.warnings.extend(fixture.warnings)
        context.durations_ms.update(
            {
                record.domain: record.duration_ms or 0
                for record in fixture.execution
                if record.selected
            }
        )
        context.completed_domains.update(planned.domain for planned in context.execution_plan)
        context.completed_steps_by_domain.update(
            {planned.domain: planned.step_count for planned in context.execution_plan}
        )

        result = assemble_endpoint_result(
            options,
            context,
            elapsed_ms=fixture.metadata.elapsed_ms,
            raw_command_capture=[],
        )

        self.assertEqual(result.metadata.selected_checks, list(profile.recommended_checks))
        self.assertEqual(result.metadata.profile_id, "dns-issue")
        self.assertEqual(result.probable_fault_domain, "dns")
        self.assertEqual(result.findings[0].identifier, "dns-failure-raw-ip-success")
        self.assertEqual(
            [record.domain for record in result.execution if record.selected],
            ["host", "time", "network", "routing", "dns", "connectivity"],
        )

    def test_storage_execution_softens_inventory_only_device_health_at_domain_level(self) -> None:
        fixture = build_default_run_result()
        fixture.facts.resources.storage_devices = [
            StorageDeviceHealth(
                device_id="disk0",
                model="Demo SSD",
                protocol="NVMe",
                medium="SSD",
                health_status=None,
                operational_status=None,
            )
        ]
        options = DiagnosticsRunOptions(
            selected_checks=["storage"],
            targets=[],
            dns_hosts=[],
        )

        execution = build_execution_records(
            fixture.facts,
            options,
            warnings=[],
            durations_ms={"storage": 10},
        )

        storage_record = next(record for record in execution if record.domain == "storage")
        device_probe = next(
            probe for probe in storage_record.probes if probe.probe_id == "storage-device-health"
        )
        self.assertEqual(storage_record.status, "passed")
        self.assertIn("Capacity checked successfully", storage_record.summary or "")
        self.assertEqual(device_probe.status, "partial")
        self.assertIn("device-health detail was not exposed", " ".join(device_probe.details).lower())
        self.assertIn("inventory collected", " ".join(device_probe.details).lower())

    def test_storage_execution_stays_partial_when_disk_usage_is_degraded(self) -> None:
        fixture = build_default_run_result()
        fixture.facts.resources.storage_devices = [
            StorageDeviceHealth(
                device_id="disk0",
                model="Demo SSD",
                protocol="NVMe",
                medium="SSD",
                health_status=None,
                operational_status=None,
            )
        ]
        options = DiagnosticsRunOptions(
            selected_checks=["storage"],
            targets=[],
            dns_hosts=[],
        )

        execution = build_execution_records(
            fixture.facts,
            options,
            warnings=[
                DiagnosticWarning(
                    domain="storage",
                    code="disk-usage-failed",
                    message="Disk usage could not be collected for path: /Volumes/External",
                )
            ],
            durations_ms={"storage": 10},
        )

        storage_record = next(record for record in execution if record.domain == "storage")
        disk_probe = next(probe for probe in storage_record.probes if probe.probe_id == "disk-usage")
        device_probe = next(
            probe for probe in storage_record.probes if probe.probe_id == "storage-device-health"
        )

        self.assertEqual(storage_record.status, "partial")
        self.assertEqual(disk_probe.status, "partial")
        self.assertEqual(device_probe.status, "partial")

    def test_storage_execution_keeps_no_device_facts_truthful_and_non_alarming(self) -> None:
        fixture = build_default_run_result()
        fixture.facts.resources.storage_devices = []
        options = DiagnosticsRunOptions(
            selected_checks=["storage"],
            targets=[],
            dns_hosts=[],
        )

        execution = build_execution_records(
            fixture.facts,
            options,
            warnings=[],
            durations_ms={"storage": 10},
        )

        storage_record = next(record for record in execution if record.domain == "storage")
        device_probe = next(
            probe for probe in storage_record.probes if probe.probe_id == "storage-device-health"
        )

        self.assertEqual(storage_record.status, "passed")
        self.assertEqual(device_probe.status, "skipped")
        self.assertIn("no storage-device health facts", " ".join(device_probe.details).lower())

    def test_registry_execution_order_is_explicit_and_deterministic(self) -> None:
        registered_order = [definition.domain for definition in iter_registered_domains()]

        self.assertEqual(
            registered_order,
            [
                "host",
                "time",
                "resources",
                "storage",
                "network",
                "routing",
                "dns",
                "connectivity",
                "services",
                "vpn",
            ],
        )


if __name__ == "__main__":
    unittest.main()
