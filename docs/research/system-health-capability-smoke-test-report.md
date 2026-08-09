# `system.health` Smoke Test Report

**Date:** 2026-08-09

**Hardware:** Raspberry Pi 5 (`sovereign.local`), the project's qualification
device, running `0.1.0-proof.3` with its real `console-health` service live.

**Status:** Real end-to-end execution of the `system.health` capability
against the live device's real `console-health` endpoint, outside its
unit-test mocks — the same kind of pass as the
[pihole capabilities smoke test](pihole-capabilities-smoke-test-report.md),
following it immediately after `system.health`'s implementation.

## Method

`sovereign_capabilities.py` and `sovereign_system.py` were copied
unmodified to a scratch directory on the device (`scp`, no privilege
needed). Unlike the Pi-hole capabilities, this one needed no `sudo`: the
`console-health` endpoint it calls
(`http://127.0.0.1:8090/api/v1/health`) requires no authentication by
design (it's the same endpoint the unauthenticated Console preview page
uses), so the assistant ran the driver script directly over its own SSH
session with no involvement from the project owner required.

## Results

```console
{
  "status": "ok",
  "result": {
    "status": "healthy",
    "checked_at": "2026-08-09T14:29:04Z",
    "system": {
      "name": "Sovereign OS",
      "version": "0.1.0-proof.3",
      "model": "Raspberry Pi 5 Model B Rev 1.1",
      "uptime_seconds": 22659,
      "memory": {"total_bytes": 17006182400, "available_bytes": 16570187776, "used_percent": 2.6},
      "data_storage": {"total_bytes": 116389072896, "available_bytes": 111348731904, "used_percent": 4.3},
      "temperature_celsius": 58.4,
      "network": [
        {"name": "eth0", "state": "up", "addresses": ["192.168.50.10"]},
        {"name": "wlan0", "state": "down", "addresses": []}
      ]
    },
    "checks": {
      "storage": {"status": "healthy", "summary": "Persistent storage available"},
      "dns": {"status": "healthy", "summary": "Resolving normally"},
      "update": {"status": "healthy", "summary": "Ready"},
      "pihole": {"status": "healthy", "summary": "Pi-hole is available"},
      "local_access": {"status": "healthy", "summary": "Console is reachable"}
    }
  }
}
--- audit ---
{"capability":"system.health","duration_seconds":0.053798,"network":"local","outcome":"executed","result_bytes":825,"side_effect":"read_only","stage_reached":"audited","timestamp":"2026-08-09T14:29:04Z","version":1}
```

The real response passed RFC-0003's full result-schema validation
without modification — confirming the schema this capability declares
(built by reading `console-health`'s source, not by guessing) genuinely
matches what the live service returns, including every nullable field's
real (non-null, in this case) shape and the two real network interfaces
this device actually has. The audit event is exactly as privacy-safe as
designed: no `system`/`checks` content, only classification and outcome.

## Limitations

Same caveat as the Pi-hole smoke test: this is a hand-driven script, not
a real caller, and only exercises the happy path already covered by the
11 mocked unit tests. It confirms the mocks accurately model the real
`console-health` response, not a substitute for qualification once this
capability is reachable through an actual Conversation Service.

## Conclusion

`system.health` behaves identically against the real `console-health`
endpoint as it does against this project's mocked test fixtures. No
discrepancy found.
