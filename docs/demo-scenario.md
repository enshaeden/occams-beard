# Demo Scenario: Verified Clock Drift and Secure-Service Risk

This is a representative deterministic walkthrough based on the current local
collector and findings behavior. It is not a customer story, a benchmark, or a
production claim.

## 1. Title

Verified clock drift that can break sign-in, TLS, or certificate-bound access.

## 2. User-visible complaint

"The internet looks fine, but sign-in or secure-service access keeps failing on
this device."

## 3. Why the case is often misdiagnosed

The symptom often gets treated as a generic DNS, VPN, proxy, or service outage
because the failure happens during authentication or TLS setup. In practice, a
materially wrong local clock can make secure workflows fail even while basic
network checks still succeed.

## 4. What Occam's Beard collects

- A local clock snapshot and UTC offset.
- Best-effort local timezone identifier and a bounded consistency check.
- One explicit HTTPS `Date` reference when the operator enables the skew check.
- Optional DNS and TCP connectivity checks that can show the broader network
  path is otherwise healthy.

## 5. What finding(s) it triggers

The gold-standard path is:

- `system-clock-materially-inaccurate`

The same run can also carry supporting healthy-context evidence from DNS and
connectivity checks, which helps keep the result grounded in collected facts
instead of speculation.

## 6. Why the finding is trustworthy

- The skew claim is only made when the HTTPS reference is certificate-validated
  in the current run.
- The collector uses a one-shot bounded midpoint calculation rather than a
  background sync subsystem or a hidden time source.
- If the HTTPS reference cannot be trusted, the result becomes inconclusive
  instead of silently downgrading certificate checks or inferring drift anyway.
- The finding remains deterministic: it is driven by the measured skew value and
  explicit thresholds already encoded in the rule set.

## 7. What the support handoff improves

The handoff becomes sharper:

- It can say the network path looked healthy enough that a generic network
  explanation is weakened.
- It can hand support or IT a concrete local-host hypothesis with supporting
  evidence instead of a vague "auth issue."
- It helps the next human responder decide whether to check local time sync,
  domain time policy, virtualization clock drift, or manual clock changes.

## 8. What remains uncertain

- A one-shot comparison does not prove how long the device has been skewed.
- It does not identify the root cause of the bad clock.
- If the HTTPS reference cannot be certificate-validated, the product can only
  say that drift could not be determined conclusively.

## 9. Why this demonstrates sound systems / endpoint diagnostics thinking

This path shows the project at its best because it avoids two common mistakes at
once:

- It does not over-attribute secure-service failures to "the network" when the
  local host state is the stronger explanation.
- It does not over-claim time drift unless the external reference is trusted in
  that same run.

That combination is a strong interview-grade example of local-first,
evidence-based endpoint diagnostics: collect only what is needed, keep the
probe bounded, make the confidence legible, and leave remediation to the human
handoff.
