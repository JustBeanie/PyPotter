# OWASP SAMM and DSOMM repository audit

Date: 2026-11-18. Scope: the `master` branch of PyPotter, its FastAPI and React code,
Docker and Compose configuration, tests, and GitHub Actions workflow. This is a
repository review, not a penetration test or an assessment of a deployed instance.
Deployment settings, reverse proxy rules, GitHub repository controls, alert response
times, and organization processes were not available for verification. The findings
below therefore do not constitute a SAMM or DSOMM maturity score.

SAMM covers governance, design, implementation, verification, and operations. DSOMM
tracks concrete DevSecOps activities. The [OWASP Cheat Sheet Series] gives the
implementation guidance used for the code findings.

## Findings and disposition

| ID | Priority | Evidence and impact | SAMM / DSOMM alignment | Disposition |
| --- | --- | --- | --- | --- |
| A-01 | High if network exposed | `pypotter/api/routes.py` has no authentication or authorization dependency. A caller able to reach `POST /api/v1/recognitions` can trigger a configured Home Assistant automation, and any caller can read history. `pypotter/cli.py` and `docker-compose.yml` bind the supplied entry points to loopback; `Dockerfile` runs Uvicorn on all container interfaces. | Design / Security Requirements; Verification / Control Verification. DSOMM Implementation / Identity and Access Management, “Enforce server-side authorization on every request.” | Open. Keep loopback binding. Before LAN or internet exposure, enforce identity and authorization at an authenticated TLS reverse proxy or in the API, including every read and action route; add negative tests. |
| A-02 | Medium | `pypotter/api/app.py` returned `str(exc)` from `/ready`. Database driver errors can contain paths, connection details, or SQL. [CodeQL alert #1] identified this flow. | SAMM Implementation / Defect Management and Verification / Requirements-driven Testing; DSOMM Test and Verification / Static depth for applications. | Fixed in this PR: the response is a generic 503; the exception is logged on the server and regression tested. |
| A-03 | Medium | `pypotter/api/app.py` returned Pydantic validation `input` and `ctx` in 422 responses. An invalid request could be reflected into the response, including large image input. | SAMM Implementation / Defect Management and Verification / Requirements-driven Testing; DSOMM Test and Verification / Static depth for applications. | Fixed in this PR: response details retain field location, type, and message while dropping input and context. |
| A-04 | Medium if untrusted image uploads are enabled | `pypotter/services/processor.py` checks dimensions and pixel count **after** `cv2.imdecode`. A small compressed image can therefore consume substantial memory during decoding before the configured pixel limit applies. Byte size is checked first. | SAMM Design / Threat Assessment and Verification / Misuse and Abuse Testing; DSOMM Test and Verification / Dynamic depth for applications. | Open. Parse image headers and reject excessive dimensions before full decode, then retain the post-decode check; test compressed oversize inputs and malformed headers. |
| A-05 | Medium if network exposed | `pypotter/api/app.py` stores one rate-limit deque per client address without a bound or expiry for the address keys. The limit is also process local, so multiple workers do not share a budget. | SAMM Design / Threat Assessment and Operations / Operational Management; DSOMM Test and Verification / Dynamic depth for applications. | Open. Enforce an edge limit for network deployments; bound and expire application-side keys or use a shared limiter. |
| A-06 | Medium | `.github/workflows/ci.yml` runs `pip-audit`, `pnpm audit`, Gitleaks, and Trivy, and pins actions to commit SHAs. It does not generate or publish the SBOM and provenance required by `docs/security.md`. `Dockerfile` and `docker-compose.yml` use mutable base-image tags. | Implementation / Secure Build and Secure Deployment; Operations / Environment Management. DSOMM Build and Deployment / Build, Deployment, and Patch Management. | Open. Add SBOM and provenance generation, pin production image digests, and document artifact verification. |
| A-07 | Low | Three `.pytest-tmp-ci/**/test.db` SQLite files are tracked in Git. They appear to be generated test artifacts; their presence creates a path for later test data to be committed inadvertently. | SAMM Implementation / Secure Build and Operations / Data Protection; DSOMM Build and Deployment / Build. | Open. Remove generated databases from tracking and ignore all `.pytest-tmp*` directories after confirming no fixture depends on them. |

The priorities above express impact under the stated exposure conditions, not a
claim that a production deployment is vulnerable. In particular, the provided
Compose and CLI configurations bind the API to loopback. A-01 and A-05 need a
deployment review before their real-world exposure can be determined.

## Evidence by practice

| Practice | Repository evidence | Unverified or missing evidence |
| --- | --- | --- |
| SAMM Governance and Design | `docs/security.md` records assets, trust boundaries, requirements, a risk register, and an incident procedure. | No evidence of policy ownership, training, periodic threat-model review, or organization-wide risk metrics. |
| SAMM Implementation / DSOMM Build and Deployment | Lockfiles, Dependabot, pinned GitHub Actions, dependency audits, secret scanning, container scanning, non-root container user, and loopback Compose ports. | SBOM, provenance, immutable base images, deployment approval, and observed secret rotation. |
| SAMM Verification / DSOMM security testing | Unit tests cover body limits, headers, Home Assistant URL policy, image magic bytes, and the error disclosures fixed here. A CodeQL alert proves at least one code-scanning analysis ran. | No evidence of authenticated-route tests, pre-decode image stress tests, dynamic application scanning, or a release gate on CodeQL alerts. |
| SAMM Operations / DSOMM operations | `docs/security.md` has an incident procedure; `/health` and `/ready` exist. | No observed deployment logs, retention, backups, recovery exercise, patch cadence, alert ownership, or incident drill. |

## Recommended next sequence

1. Decide and document the supported network exposure model. Keep the default
   loopback deployment until authenticated TLS access control has a tested owner.
2. Prevent full image decoding before pixel limits can be checked, and add an
   abuse test for highly compressed oversized images.
3. Put rate limiting at the trusted edge for any networked deployment and bound
   application-side state.
4. Complete the promised supply-chain evidence: SBOM, provenance, and immutable
   runtime image references. Remove generated databases from source tracking.
5. Review this register at each release and record owners, remediation dates, and
   deployment evidence. Use SAMM or DSOMM scoring only with process and runtime
   evidence, not repository files alone.

## Verification in this review

- 15 Python tests passed, including the two new disclosure regression tests.
- Ruff check and format, mypy, and the OpenAPI contract check passed.
- `pip-audit` and `pnpm audit --audit-level high` reported no known vulnerable
  dependencies on 2026-11-18. The local `pypotter` package itself is not on PyPI
  and was skipped by `pip-audit`.

## References

- [OWASP SAMM model](https://owaspsamm.org/model/)
- [OWASP SAMM requirements-driven testing](https://owaspsamm.org/model/verification/requirements-driven-testing/)
- [OWASP SAMM defect management](https://owaspsamm.org/model/implementation/defect-management/)
- [OWASP DSOMM usage and scope](https://dsomm.owasp.org/usage)
- [OWASP DSOMM activity mapping](https://dsomm.owasp.org/mapping)
- [OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/index.html)
- [OWASP Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html)
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [CodeQL alert #1](https://github.com/JustBeanie/PyPotter/security/code-scanning/1)
