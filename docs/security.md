# Security baseline and operational playbook

This document is the lightweight security evidence pack for PyPotter. The app is
local-first, but any bind address other than loopback must be treated as a
networked service.

## Threat model

### Assets

- Home Assistant bearer token and MQTT credentials.
- The ability to trigger Home Assistant automations.
- Recognition history and service availability.
- CI credentials, build artifacts, dependency metadata, and source code.

### Trust boundaries and actors

| Boundary | Actor/threat | Security objective |
| --- | --- | --- |
| Browser/API -> FastAPI | Unauthenticated or hostile LAN client | Authenticate access, validate input, limit resource use |
| FastAPI -> OpenCV | Malformed or decompression-bomb image | Bound bytes, dimensions, pixels, and processing cost |
| FastAPI -> Home Assistant | Misconfigured or compromised endpoint | HTTPS/localhost allowlist, no credential forwarding on redirects |
| FastAPI -> MQTT | Rogue client or broker | Credentials, TLS for remote brokers, topic authorization |
| CI -> package/container registry | Dependency or workflow compromise | Lockfiles, scanning, SBOM, provenance, immutable references |

## Security requirements

1. Network-exposed API deployments MUST use an authentication layer and TLS.
2. Request bodies and decoded image bytes MUST be bounded before expensive work.
3. Only PNG/JPEG images within configured byte, dimension, and pixel limits are accepted.
4. Home Assistant URLs MUST be HTTPS, except loopback HTTP for local development; redirects are disabled.
5. MQTT MUST use credentials. Remote brokers MUST use TLS. Anonymous broker access is prohibited.
6. API responses MUST include browser hardening headers; production responses MUST include HSTS.
7. Requests MUST be rate-limited and security-relevant events MUST be emitted without secrets.
8. CI MUST audit dependencies, scan images, generate SBOM/provenance, and prevent secret leakage.

## Risk register

| ID | Risk | Owner | Treatment | Status |
| --- | --- | --- | --- | --- |
| R-01 | Unauthorized spell casts/history access | Application owner | Deploy auth/reverse proxy; keep default bind loopback | Open for networked deployment |
| R-02 | Image/body resource exhaustion | Application owner | Enforced body, byte, dimension, pixel, and rate limits | Mitigated in code |
| R-03 | Home Assistant token disclosure via redirect | Application owner | HTTPS/loopback validation and `allow_redirects=False` | Mitigated in code |
| R-04 | MQTT interception/spoofing | Operations owner | Credentials always; TLS for non-loopback; broker anonymous off | Mitigated in code/config |
| R-05 | Browser injection/clickjacking | Application owner | CSP, frame denial, MIME/referrer policies | Mitigated in code |
| R-06 | Compromised dependency/build artifact | Release owner | Audit, SBOM, image scan, provenance, immutable pins | CI enforcement required |

## Incident procedure

1. Disable external exposure and set `PYPOTTER_ENABLE_HOME_ASSISTANT=false` and
   `PYPOTTER_ENABLE_MQTT=false` if abuse or credential compromise is suspected.
2. Preserve application/container logs and the relevant CI run; do not publish
   bearer tokens, passwords, request bodies, or image data.
3. Rotate Home Assistant and MQTT credentials, then verify broker ACLs and
   Home Assistant automation history.
4. Check recognition history, rate-limit events, failed validation events, and
   outbound integration failures for the incident window.
5. Rebuild from a reviewed commit, re-run security checks, and redeploy with
   loopback binding or an authenticated TLS reverse proxy.
6. Record root cause, affected assets, timeline, containment, and corrective
   actions in the risk register; review the threat model after closure.

## Production HTTPS guidance

Terminate TLS at a maintained reverse proxy or ingress, enforce HTTPS redirects
there, restrict the upstream to a private network, and preserve only the
validated client identity headers. Do not expose Uvicorn directly to the public
internet. HSTS is enabled by the app only when `PYPOTTER_ENVIRONMENT=production`.
