"""Tests for JSON serialization."""

from __future__ import annotations

import json
import tempfile
import unittest

from occams_beard.models import (
    CollectedFacts,
    ConnectivityState,
    CpuState,
    DnsState,
    EndpointDiagnosticResult,
    HostBasics,
    MemoryState,
    Metadata,
    NetworkState,
    PlatformInfo,
    ProcessCategoryLoad,
    ProcessSnapshot,
    ResourceState,
    RouteSummary,
    ServiceState,
    VpnState,
)
from occams_beard.serializers import to_json_dict, write_json_file


def build_result() -> EndpointDiagnosticResult:
    """Create a minimal result object for serializer tests."""

    facts = CollectedFacts(
        host=HostBasics(
            hostname="demo-host",
            operating_system="Linux",
            kernel="6.8.0",
            current_user="operator",
            uptime_seconds=100,
        ),
        resources=ResourceState(
            cpu=CpuState(
                logical_cpus=4,
                utilization_percent_estimate=20.0,
                load_ratio_1m=0.2,
                saturation_level="normal",
            ),
            memory=MemoryState(
                total_bytes=1000,
                available_bytes=500,
                free_bytes=400,
                pressure_level="normal",
                available_percent=50.0,
                swap_total_bytes=200,
                swap_free_bytes=120,
                swap_used_bytes=80,
                committed_bytes=600,
                commit_limit_bytes=1200,
                commit_pressure_level="normal",
            ),
            disks=[],
            process_snapshot=ProcessSnapshot(
                sampled_process_count=12,
                high_cpu_process_count=1,
                high_memory_process_count=1,
                top_categories=[
                    ProcessCategoryLoad(
                        category="browser",
                        process_count=1,
                        combined_cpu_percent_estimate=62.0,
                        combined_memory_bytes=400,
                    )
                ],
            ),
        ),
        network=NetworkState(
            route_summary=RouteSummary(
                default_gateway="192.168.1.1",
                default_interface="eth0",
                has_default_route=True,
                routes=[],
            )
        ),
        dns=DnsState(),
        connectivity=ConnectivityState(internet_reachable=True),
        vpn=VpnState(),
        services=ServiceState(),
    )
    return EndpointDiagnosticResult(
        metadata=Metadata(
            project_name="occams-beard",
            version="0.1.0",
            generated_at="2026-04-01T00:00:00+00:00",
            elapsed_ms=100,
            selected_checks=["network"],
        ),
        platform=PlatformInfo(
            system="Linux",
            release="6.8.0",
            version="demo",
            machine="x86_64",
            python_version="3.11.9",
        ),
        facts=facts,
        probable_fault_domain="healthy",
    )


class SerializerTests(unittest.TestCase):
    """Validate JSON serializer output."""

    def test_to_json_dict_contains_expected_sections(self) -> None:
        result = build_result()

        payload = to_json_dict(result)

        self.assertEqual(payload["schema_version"], "1.3.0")
        self.assertIn("metadata", payload)
        self.assertIn("facts", payload)
        self.assertEqual(payload["platform"]["system"], "Linux")
        self.assertNotIn("raw_command_capture", payload)
        self.assertIn("battery", payload["facts"]["resources"])
        self.assertIn("storage_devices", payload["facts"]["resources"])
        self.assertIn("process_snapshot", payload["facts"]["resources"])
        self.assertIn("swap_used_bytes", payload["facts"]["resources"]["memory"])

    def test_write_json_file_persists_valid_json(self) -> None:
        result = build_result()

        with tempfile.TemporaryDirectory() as tempdir:
            output_path = write_json_file(result, f"{tempdir}/report.json")
            loaded = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(loaded["metadata"]["project_name"], "occams-beard")
        self.assertEqual(loaded["facts"]["host"]["hostname"], "demo-host")


if __name__ == "__main__":
    unittest.main()
