"""Resource-, storage-, and hardware-focused deterministic findings rules."""

from __future__ import annotations

from occams_beard.findings_common import (
    dedupe_preserve_order,
    format_bytes,
    format_process_category,
    format_ratio,
    format_tcp_targets,
    network_explanation_not_supported,
    network_health_evidence,
)
from occams_beard.models import CollectedFacts, Finding, StorageDeviceHealth
from occams_beard.utils.validation import is_private_or_loopback_host


def evaluate_resource_pressure(
    facts: CollectedFacts,
    *,
    enabled_checks: set[str] | None = None,
    issue_category: str | None = None,
) -> list[Finding]:
    resources = facts.resources
    findings: list[Finding] = []
    memory = resources.memory
    enabled_checks = enabled_checks or set()
    cpu_pressure = cpu_pressure_state(resources.cpu)
    memory_pressure = memory_pressure_state(memory)
    process_snapshot = resources.process_snapshot
    local_pressure_present = cpu_pressure["present"] or memory_pressure["present"]
    combined_pressure = cpu_pressure["present"] and memory_pressure["present"]
    strong_local_pressure = bool(cpu_pressure["strong"] or memory_pressure["strong"])
    weakens_network_explanation = network_explanation_not_supported(
        facts,
        enabled_checks=enabled_checks,
    )
    findings.extend(storage_space_findings(facts, enabled_checks=enabled_checks))

    if strong_local_pressure and issue_category == "device slow":
        findings.append(
            Finding(
                identifier="device-slow-local-host-pressure",
                severity="high"
                if cpu_pressure["strong"] and memory_pressure["strong"]
                else "medium",
                title="Local resource pressure is likely contributing to the device feeling slow",
                summary=(
                    "The current host snapshot shows resource pressure that lines up with the "
                    "reported slowness."
                ),
                evidence=host_pressure_evidence(
                    facts,
                    include_network_context=weakens_network_explanation,
                ),
                probable_cause=(
                    "The endpoint appears overloaded in the current snapshot, so local host "
                    "pressure is a more credible explanation for the reported slowness than a "
                    "generic network-only problem."
                ),
                fault_domain="local_host",
                confidence=0.93 if combined_pressure else 0.87,
            )
        )

    if memory_pressure["strong"]:
        findings.append(
            Finding(
                identifier="high-memory-pressure",
                severity="high" if memory_pressure["severity"] == "high" else "medium",
                title="Severe local memory pressure is likely affecting responsiveness",
                summary=(
                    "Available memory is low enough that the operating system may be spending "
                    "time reclaiming memory or leaning on swap."
                ),
                evidence=memory_pressure_evidence(memory, process_snapshot),
                probable_cause=(
                    "Local memory pressure is likely contributing to sluggish applications, "
                    "slow task switching, or delayed input response."
                ),
                fault_domain="local_host",
                confidence=0.9 if memory.commit_pressure_level == "high" else 0.84,
            )
        )

    if cpu_pressure["strong"]:
        findings.append(
            Finding(
                identifier="sustained-cpu-saturation",
                severity="high" if combined_pressure else "medium",
                title="Sustained CPU saturation is likely affecting responsiveness",
                summary=(
                    "Runnable CPU work is staying at or above the available logical-core "
                    "capacity in the current snapshot."
                ),
                evidence=cpu_pressure_evidence(resources.cpu, process_snapshot),
                probable_cause=(
                    "The host currently has more CPU demand than available execution capacity, "
                    "which is likely to slow interactive work."
                ),
                fault_domain="local_host",
                confidence=0.9 if combined_pressure else 0.83,
            )
        )

    if (
        local_pressure_present
        and not strong_local_pressure
        and (
            combined_pressure
            or snapshot_shows_multiple_pressure_vectors(process_snapshot)
        )
    ):
        findings.append(
            Finding(
                identifier="local-resource-pressure-no-dominant-source",
                severity="medium",
                title=(
                    "Local resource pressure is present, but no single dominant source stands out"
                ),
                summary=(
                    "The device shows moderate host-pressure signals, but this snapshot does not "
                    "cleanly isolate one bottleneck."
                ),
                evidence=host_pressure_evidence(
                    facts,
                    include_network_context=weakens_network_explanation,
                ),
                probable_cause=(
                    "The endpoint may be overloaded right now, but the current one-shot snapshot "
                    "is not strong enough to attribute the pressure to CPU alone or memory alone."
                ),
                fault_domain="local_host",
                confidence=0.7,
            )
        )

    if strong_local_pressure and has_degraded_connectivity(facts):
        findings.append(
            Finding(
                identifier="host-pressure-with-connectivity-degradation",
                severity="medium",
                title="Resource pressure may be contributing to degraded connectivity",
                summary=(
                    "The endpoint is under local resource pressure while connectivity checks are "
                    "also degraded."
                ),
                evidence=host_pressure_evidence(facts) + [connectivity_pressure_evidence(facts)],
                probable_cause=(
                    "Host saturation may be contributing to socket timeouts, "
                    "slow name resolution, or delayed operator workflows, "
                    "though upstream issues may still exist."
                ),
                fault_domain="local_host",
                confidence=0.67,
                heuristic=True,
            )
        )

    if issue_category == "device slow" and not local_pressure_present:
        findings.append(
            Finding(
                identifier="no-significant-host-pressure",
                severity="info",
                title="No significant host-pressure signal was detected",
                summary=(
                    "This run did not capture strong CPU, memory, swap, or bounded process-load "
                    "evidence that would explain the device feeling slow."
                ),
                evidence=no_host_pressure_evidence(resources),
                probable_cause=(
                    "The current snapshot does not support a local resource-pressure explanation "
                    "on its own."
                ),
                fault_domain="healthy",
                confidence=0.76,
            )
        )

    if issue_category == "device slow" and weakens_network_explanation:
        findings.append(
            Finding(
                identifier="network-explanation-not-supported",
                severity="info",
                title="Selected network checks do not currently explain the reported slowness",
                summary=(
                    "The network checks collected in this run do not show a matching network "
                    "failure signature."
                ),
                evidence=network_health_evidence(facts, enabled_checks=enabled_checks),
                probable_cause=(
                    "Current evidence does not support a network-based explanation for the "
                    "reported slowness."
                ),
                fault_domain="healthy",
                confidence=0.8,
            )
        )

    if issue_category == "low disk space" and not storage_issue_present(resources):
        findings.append(
            Finding(
                identifier="no-significant-storage-pressure",
                severity="info",
                title="Current storage evidence does not support a strong local storage explanation",
                summary=(
                    "This run did not capture critically low free space or a device-health state "
                    "that would strongly explain the reported issue."
                ),
                evidence=no_storage_pressure_evidence(resources)
                + (
                    network_health_evidence(facts, enabled_checks=enabled_checks)
                    if network_explanation_not_supported(
                        facts,
                        enabled_checks=enabled_checks,
                    )
                    else []
                ),
                probable_cause=(
                    "The current snapshot does not support local storage exhaustion or exposed "
                    "storage-device degradation as the dominant explanation."
                ),
                fault_domain="healthy",
                confidence=0.78,
            )
        )

    return findings


def evaluate_hardware_health(facts: CollectedFacts) -> list[Finding]:
    findings: list[Finding] = []
    battery = facts.resources.battery
    if (
        battery is not None
        and battery.present
        and battery_condition_is_degraded(battery.condition)
    ):
        findings.append(
            Finding(
                identifier="battery-health-degraded",
                severity="medium",
                title="Battery health needs attention",
                summary=(
                    "The operating system reported a degraded battery condition on this endpoint."
                ),
                evidence=[
                    f"Battery condition is reported as {battery.condition}.",
                    (
                        "Battery health is reported as "
                        f"{battery.health_percent:.1f}% of design capacity."
                        if battery.health_percent is not None
                        else "Battery design-capacity percentage was not reported."
                    ),
                ]
                + (
                    [f"Battery cycle count is {battery.cycle_count}."]
                    if battery.cycle_count is not None
                    else []
                ),
                probable_cause=(
                    "The local battery is reporting a service or degradation state, "
                    "which can contribute to unstable local device behavior."
                ),
                fault_domain="local_host",
                confidence=0.87,
            )
        )

    failed_devices = [
        device
        for device in facts.resources.storage_devices
        if storage_device_status(device) == "failure"
    ]
    warning_devices = [
        device
        for device in facts.resources.storage_devices
        if storage_device_status(device) == "warning"
    ]

    if failed_devices:
        findings.append(
            Finding(
                identifier="storage-device-health-failure",
                severity="high",
                title="Storage-device health reports a failing state",
                summary=(
                    "At least one storage device reported an explicit failing or unhealthy state."
                ),
                evidence=storage_device_evidence(failed_devices),
                probable_cause=(
                    "The local storage subsystem is reporting a device-level fault that may "
                    "affect local reads, writes, boot behavior, or application stability."
                ),
                fault_domain="local_host",
                confidence=0.93,
            )
        )
    elif warning_devices:
        findings.append(
            Finding(
                identifier="storage-device-health-warning",
                severity="medium",
                title="Storage-device health reports a degraded state",
                summary=(
                    "At least one storage device reported a warning state even though it is not "
                    "yet marked failed."
                ),
                evidence=storage_device_evidence(warning_devices),
                probable_cause=(
                    "The local storage subsystem is signaling degraded device health that may "
                    "become operationally significant even without a total device failure."
                ),
                fault_domain="local_host",
                confidence=0.82,
            )
        )

    return findings


def storage_space_findings(
    facts: CollectedFacts,
    *,
    enabled_checks: set[str],
) -> list[Finding]:
    findings: list[Finding] = []
    weakens_network_explanation = network_explanation_not_supported(
        facts,
        enabled_checks=enabled_checks,
    )
    for disk in facts.resources.disks:
        pressure_level = disk_pressure_level(disk)
        if pressure_level not in {"critical", "low"}:
            continue

        operational_impact = storage_operational_impact(disk)
        evidence = disk_pressure_evidence(disk)
        if operational_impact is not None:
            evidence.append(operational_impact)
        if weakens_network_explanation:
            evidence.extend(network_health_evidence(facts, enabled_checks=enabled_checks))

        if pressure_level == "critical":
            findings.append(
                Finding(
                    identifier="critical-disk-space-exhaustion",
                    severity="high",
                    title=f"Critical disk-space exhaustion on {disk.path}",
                    summary=(
                        "Available disk space is critically low and may affect application "
                        "stability."
                    ),
                    evidence=evidence,
                    probable_cause=(
                        "Local filesystem space exhaustion is likely to affect writes, temp "
                        "files, logging, updates, or sign-in caches on this device."
                    ),
                    fault_domain="local_host",
                    confidence=0.95 if is_operational_volume(disk) else 0.88,
                    plain_language=(
                        "Available disk space is critically low and may affect application "
                        "stability."
                    ),
                    safe_next_actions=[
                        (
                            "Remove or archive only known non-essential local files if that is "
                            "already part of the documented operator process."
                        ),
                        "Capture a support bundle before cleanup if the storage pressure is current.",
                    ],
                    escalation_triggers=[
                        "Escalate if critical free-space pressure remains on an operational volume.",
                    ],
                    uncertainty_notes=[
                        (
                            "This is a current capacity snapshot only; it does not prove how long "
                            "the filesystem has been this full."
                        )
                    ],
                )
            )
        else:
            findings.append(
                Finding(
                    identifier="low-disk-space-operational-risk",
                    severity="medium",
                    title=f"Low available disk space may affect local operations on {disk.path}",
                    summary=(
                        "Available disk space is low enough that local writes, logs, or updates "
                        "may start failing."
                    ),
                    evidence=evidence,
                    probable_cause=(
                        "Local storage pressure may be contributing to application failures, "
                        "unstable updates, delayed writes, or missing local logs."
                    ),
                    fault_domain="local_host",
                    confidence=0.9 if is_operational_volume(disk) else 0.8,
                    plain_language=(
                        "Low available disk space may impact local writes, logs, or updates."
                    ),
                    safe_next_actions=[
                        (
                            "Review obvious non-essential local files first before deleting any "
                            "managed or application data."
                        ),
                        "Capture a support bundle while the low-space condition is still present.",
                    ],
                    escalation_triggers=[
                        "Escalate if low free space persists on a system or user-data volume.",
                    ],
                    uncertainty_notes=[
                        (
                            "This finding identifies storage pressure, not which application will "
                            "fail first or which file set caused the pressure."
                        )
                    ],
                )
            )
    return findings


def battery_condition_is_degraded(condition: str | None) -> bool:
    if condition is None:
        return False
    normalized = condition.strip().lower()
    degraded_markers = (
        "replace",
        "service",
        "poor",
        "check battery",
        "failure",
        "failing",
        "degraded",
        "dead",
        "overheat",
    )
    return any(marker in normalized for marker in degraded_markers)


def storage_device_status(device: StorageDeviceHealth) -> str | None:
    raw_statuses = [
        status.strip().lower()
        for status in (device.health_status, device.operational_status)
        if status
    ]
    failure_markers = ("fail", "failing", "failed", "unhealthy", "critical")
    warning_markers = ("warning", "degraded", "predictive failure")
    healthy_markers = ("healthy", "verified", "ok")
    if any(any(marker in status for marker in failure_markers) for status in raw_statuses):
        return "failure"
    if any(any(marker in status for marker in warning_markers) for status in raw_statuses):
        return "warning"
    if raw_statuses and all(
        any(marker in status for marker in healthy_markers) for status in raw_statuses
    ):
        return "healthy"
    return None


def storage_issue_present(resources) -> bool:
    if any(disk_pressure_level(disk) in {"critical", "low"} for disk in resources.disks):
        return True
    return any(
        storage_device_status(device) in {"failure", "warning"}
        for device in resources.storage_devices
    )


def disk_pressure_level(disk) -> str:
    if disk.pressure_level in {"critical", "low", "normal"}:
        return str(disk.pressure_level)
    if disk.total_bytes <= 0:
        return "unknown"
    free_ratio = disk.free_bytes / disk.total_bytes
    if free_ratio <= 0.05 or disk.free_bytes <= 2 * 1024**3:
        return "critical"
    if free_ratio <= 0.10 or disk.free_bytes <= 10 * 1024**3:
        return "low"
    return "normal"


def disk_pressure_evidence(disk) -> list[str]:
    free_percent = (
        f"{disk.free_percent:.1f}%"
        if disk.free_percent is not None
        else format_ratio(disk.free_bytes, disk.total_bytes)
    )
    return [
        f"Filesystem {disk.path} is {disk.percent_used:.1f}% utilized.",
        f"Free space is {format_bytes(disk.free_bytes)} ({free_percent} free).",
        f"Storage pressure classification for this volume is {disk_pressure_level(disk)}.",
    ]


def storage_operational_impact(disk) -> str | None:
    role_hint = disk.role_hint or "other"
    if role_hint == "system":
        return (
            "This appears to be a system-facing volume, so low space can affect temp files, "
            "logs, updates, caches, or sign-in state."
        )
    if role_hint == "user_data":
        return (
            "This appears to be a user-data volume, so low space can affect profile data, "
            "downloads, caches, and application writes."
        )
    return (
        "Low space on this monitored volume may still affect local writes for applications that "
        "store data there."
    )


def is_operational_volume(disk) -> bool:
    return disk.role_hint in {"system", "user_data"}


def storage_device_evidence(devices: list[StorageDeviceHealth]) -> list[str]:
    evidence: list[str] = []
    for device in devices:
        labels = [device.device_id]
        if device.model:
            labels.append(device.model)
        status_bits = [
            value
            for value in (
                device.health_status,
                device.operational_status,
                device.protocol,
                device.medium,
            )
            if value
        ]
        evidence.append(
            "Storage device "
            f"{' / '.join(labels)} reports "
            f"{'; '.join(status_bits) or 'an explicit health issue'}."
        )
    return evidence


def no_storage_pressure_evidence(resources) -> list[str]:
    if not resources.disks and not resources.storage_devices:
        return ["No disk-capacity or storage-device health facts were collected in this run."]

    evidence: list[str] = []
    if resources.disks:
        healthiest = [
            (
                f"{disk.path} ({disk.free_percent:.1f}% free, "
                f"{disk_pressure_level(disk)} pressure)"
            )
            for disk in resources.disks[:3]
            if disk.free_percent is not None
        ]
        if healthiest:
            evidence.append(f"Monitored volumes: {', '.join(healthiest)}.")
    healthy_devices = [
        device
        for device in resources.storage_devices
        if storage_device_status(device) == "healthy"
    ]
    if healthy_devices:
        evidence.append(
            "Storage-device health reported healthy state for "
            + ", ".join(device.device_id for device in healthy_devices[:3])
            + "."
        )
    elif not resources.storage_devices:
        evidence.append("Storage-device health was not exposed on this endpoint.")
    return evidence or ["No strong local storage-risk signal was detected."]


def has_degraded_connectivity(facts: CollectedFacts) -> bool:
    failed_public_tcp = [
        check
        for check in facts.connectivity.tcp_checks
        if not check.success and not is_private_or_loopback_host(check.target.host)
    ]
    return not facts.connectivity.internet_reachable or len(failed_public_tcp) >= 2


def connectivity_pressure_evidence(facts: CollectedFacts) -> str:
    failed_public_tcp = [
        check
        for check in facts.connectivity.tcp_checks
        if not check.success and not is_private_or_loopback_host(check.target.host)
    ]
    if failed_public_tcp:
        return f"External TCP failures were observed: {format_tcp_targets(failed_public_tcp)}."
    return "Internet reachability checks did not succeed."


def cpu_pressure_state(cpu) -> dict[str, bool | str]:
    logical_cpus = cpu.logical_cpus or 0
    ratio_5m = (
        (cpu.load_average_5m / logical_cpus)
        if cpu.load_average_5m is not None and logical_cpus > 0
        else None
    )
    strong = bool(
        cpu.load_ratio_1m is not None
        and cpu.load_ratio_1m >= 1.25
        and ratio_5m is not None
        and ratio_5m >= 1.0
    )
    present = strong or cpu.saturation_level == "elevated"
    return {
        "present": present,
        "strong": strong,
        "ratio_5m_known": ratio_5m is not None,
    }


def memory_pressure_state(memory) -> dict[str, bool | str]:
    available_percent = memory.available_percent or 0.0
    swap_pressure = has_swap_pressure(memory)
    commit_pressure = memory.commit_pressure_level in {"high", "elevated"}
    strong = bool(
        memory.pressure_level == "high"
        and (
            available_percent <= 8.0
            or swap_pressure
            or memory.commit_pressure_level == "high"
        )
    )
    present = strong or memory.pressure_level == "elevated" or commit_pressure or swap_pressure
    severity = (
        "high"
        if available_percent <= 5.0 or memory.commit_pressure_level == "high"
        else "medium"
    )
    return {
        "present": present,
        "strong": strong,
        "severity": severity,
    }


def has_swap_pressure(memory) -> bool:
    if memory.swap_used_bytes is None:
        return False
    if memory.swap_total_bytes:
        return (
            memory.swap_total_bytes > 0
            and (memory.swap_used_bytes / memory.swap_total_bytes) >= 0.25
        )
    return memory.swap_used_bytes >= 512 * 1024**2


def snapshot_shows_multiple_pressure_vectors(snapshot) -> bool:
    if snapshot is None:
        return False
    vectors = 0
    if snapshot.high_cpu_process_count >= 2:
        vectors += 1
    if snapshot.high_memory_process_count >= 2:
        vectors += 1
    if len(snapshot.top_categories) >= 2:
        vectors += 1
    return vectors >= 2


def host_pressure_evidence(
    facts: CollectedFacts,
    *,
    include_network_context: bool = False,
) -> list[str]:
    evidence: list[str] = []
    evidence.extend(
        cpu_pressure_evidence(
            facts.resources.cpu,
            facts.resources.process_snapshot,
        )
    )
    evidence.extend(
        memory_pressure_evidence(
            facts.resources.memory,
            facts.resources.process_snapshot,
        )
    )
    snapshot = facts.resources.process_snapshot
    if snapshot is not None and snapshot.sampled_process_count:
        evidence.append(
            "Bounded process snapshot sampled "
            f"{snapshot.sampled_process_count} processes and retained "
            f"{len(snapshot.top_categories)} notable category summaries."
        )
    if include_network_context:
        evidence.extend(
            network_health_evidence(
                facts,
                enabled_checks={"routing", "dns", "connectivity"},
            )
        )
    return dedupe_preserve_order(evidence)


def cpu_pressure_evidence(cpu, snapshot) -> list[str]:
    evidence: list[str] = []
    if cpu.logical_cpus is not None:
        evidence.append(f"Logical CPU count is {cpu.logical_cpus}.")
    if cpu.load_average_1m is not None:
        evidence.append(
            "1-minute load average is "
            f"{cpu.load_average_1m:.2f}"
            + (
                f" ({cpu.load_ratio_1m:.2f}x logical-core capacity)."
                if cpu.load_ratio_1m is not None
                else "."
            )
        )
    if cpu.load_average_5m is not None:
        evidence.append(f"5-minute load average is {cpu.load_average_5m:.2f}.")
    if cpu.saturation_level is not None:
        evidence.append(f"CPU saturation classification is {cpu.saturation_level}.")
    if snapshot is not None and snapshot.high_cpu_process_count:
        evidence.append(
            "Bounded process snapshot found "
            f"{snapshot.high_cpu_process_count} unusually active processes."
        )
    for category in (snapshot.top_categories[:2] if snapshot is not None else []):
        if category.combined_cpu_percent_estimate is None:
            continue
        evidence.append(
            f"Process category {format_process_category(category.category)} accounts for about "
            f"{category.combined_cpu_percent_estimate:.1f}% sampled CPU."
        )
    return evidence


def memory_pressure_evidence(memory, snapshot) -> list[str]:
    evidence: list[str] = []
    if memory.available_percent is not None:
        evidence.append(f"Available memory is {memory.available_percent:.1f}% of total RAM.")
    if memory.pressure_level is not None:
        evidence.append(f"Memory pressure classification is {memory.pressure_level}.")
    if memory.swap_used_bytes is not None or memory.swap_total_bytes is not None:
        evidence.append(
            f"Swap usage is {format_bytes(memory.swap_used_bytes)} / "
            f"{format_bytes(memory.swap_total_bytes)}."
        )
    if memory.committed_bytes is not None and memory.commit_limit_bytes is not None:
        evidence.append(
            f"Committed memory is {format_bytes(memory.committed_bytes)} / "
            f"{format_bytes(memory.commit_limit_bytes)}."
        )
    if memory.commit_pressure_level is not None:
        evidence.append(f"Commit pressure classification is {memory.commit_pressure_level}.")
    if snapshot is not None and snapshot.high_memory_process_count:
        evidence.append(
            "Bounded process snapshot found "
            f"{snapshot.high_memory_process_count} unusually large resident-memory consumers."
        )
    for category in (snapshot.top_categories[:2] if snapshot is not None else []):
        if category.combined_memory_bytes is None:
            continue
        evidence.append(
            f"Process category {format_process_category(category.category)} holds about "
            f"{format_bytes(category.combined_memory_bytes)} of sampled resident memory."
        )
    return evidence


def no_host_pressure_evidence(resources) -> list[str]:
    evidence = []
    evidence.append(
        f"CPU saturation classification is {resources.cpu.saturation_level or 'unknown'}."
    )
    evidence.append(
        f"Memory pressure classification is {resources.memory.pressure_level or 'unknown'}."
    )
    if resources.memory.commit_pressure_level is not None:
        evidence.append(
            f"Commit pressure classification is {resources.memory.commit_pressure_level}."
        )
    snapshot = resources.process_snapshot
    if snapshot is None:
        evidence.append("Bounded process-load hints were unavailable in this snapshot.")
    else:
        evidence.append(
            f"Bounded process snapshot found {snapshot.high_cpu_process_count} high-CPU and "
            f"{snapshot.high_memory_process_count} high-memory processes."
        )
    return evidence
