# Pi-hole API Assessment

**Status:** Planned  
**Initial target:** Pi-hole v6

## Question

Which supported Pi-hole APIs, authentication method, permissions, and response semantics can safely implement the preview's read-only use cases?

## Required Investigation

- Official API documentation and version discovery
- Authentication and session behavior
- Health and summary-statistics endpoints
- Top-client and blocking-detail endpoints
- Pagination, limits, time ranges, and time zones
- Error, timeout, and rate-limit behavior
- Least-privilege or read-only credential support
- Compatibility across candidate Pi-hole v6 versions
- Sensitive fields that require minimization or redaction
- Behavior when Pi-hole is remote versus on the same host

## Required Output

- Endpoint-to-use-case mapping
- Example sanitized requests and responses
- Typed error taxonomy
- Compatibility statement
- Credential and data-handling requirements
- Gaps that remove a use case from preview scope

## Decision Informed

Pi-hole integration RFC and capability contracts.

