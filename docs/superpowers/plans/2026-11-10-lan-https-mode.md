# J.A.R.V.I.S. HTTPS LAN Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit HTTPS access to J.A.R.V.I.S. from another computer on a private LAN without changing normal loopback startup.

**Architecture:** The launcher accepts `--lan --lan-host <private-ip>`, validates one assigned private IPv4 address, creates a local CA and IP-matched server certificate below `.runtime/certs`, and starts Uvicorn TLS on that exact address. FastAPI allows only the exact HTTPS origin and Host and enables Secure cookies; the Hermes plugin connects to that endpoint using the CA while retaining its bearer token.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, Python `ssl`/`ipaddress`, OpenSSL, Bash/npm, pytest.

**Spec:** `docs/superpowers/specs/2026-11-10-lan-https-mode-design.md`

## Global Constraints

- Normal `npm start` must keep the backend bound to `127.0.0.1`.
- Hermes API and Ollama remain loopback-only.
- LAN binds must use one assigned RFC1918 IPv4 address; never `0.0.0.0`.
- LAN mode requires direct HTTPS, exact Host/Origin checks, and Secure browser cookies.
- The Hermes plugin must retain bearer authentication and verify the generated local CA.
- No firewall, router, global trust-store, or persistent startup changes.
- Runtime keys/certificates stay under ignored `.runtime/` and never enter Git.

## Review Focus

- Public, wildcard, loopback, link-local, reserved, and unassigned IP input must fail closed; test address and bind validation.
- HTTPS must not accept a mismatched SAN, expired certificate, insecure CA path, or missing private key; test generation and TLS loading.
- A LAN Host with an unrelated Origin (or vice versa) must be rejected; test middleware with ASGI requests.
- Session cookies must be Secure only in LAN mode and remain compatible with loopback mode; test login headers in both modes.
- The Hermes plugin must never disable TLS verification or drop its bearer token; test both loopback and LAN URL construction/auth.

---

### Task 1: LAN address and certificate lifecycle

**Files:**
- Create: `backend/app/lan.py`
- Create: `backend/tests/test_lan.py`
- Modify: `scripts/run.py`

**Interfaces:**
- `validate_lan_host(host: str) -> str` returns a normalized assigned private IPv4 or raises `ValueError`.
- `ensure_lan_certificate(host: str, state_dir: Path) -> tuple[Path, Path, Path]` returns `(ca_cert, server_cert, server_key)` and verifies the leaf SAN/issuer/key before use.

- [x] Write tests for valid private IPv4, invalid address classes, unassigned addresses, certificate generation, SAN match, CA verification, and file permissions.
- [x] Run `pytest backend/tests/test_lan.py -q` and confirm the missing interfaces fail as expected.
- [x] Implement address validation and OpenSSL-backed, private runtime certificate generation.
- [x] Re-run the focused tests and verify they pass.

### Task 2: Backend HTTPS security policy

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_security.py`
- Modify: `backend/tests/test_lan.py`

**Interfaces:**
- `Settings` gains explicit LAN mode, LAN host, HTTPS origin, and a `secure_cookie` property.
- The app derives its trusted Host and Origin allowlists from that validated mode.

- [x] Add failing tests for exact LAN Host/Origin acceptance, mismatches, and Secure cookie behavior, while retaining existing loopback expectations.
- [x] Run the focused security tests and confirm the failures exercise the missing policy.
- [x] Implement exact Host/Origin policy and mode-dependent cookie security.
- [x] Run focused tests and then the full backend pytest suite.

### Task 3: Launcher and Hermes plugin transport

**Files:**
- Modify: `scripts/run.py`
- Modify: `scripts/start.sh`
- Modify: `scripts/common.sh`
- Modify: `scripts/record-process.py`
- Modify: `backend/app/process_control.py`
- Modify: `hermes/plugins/jarvis_desktop/__init__.py`
- Modify: `backend/tests/test_process_control.py`
- Create: `backend/tests/test_lan_launcher.py`

**Interfaces:**
- `npm start -- --lan --lan-host <private-ip>` is opt-in; `--lan` without the host fails with an actionable message.
- Backend process records pin the exact bind host and TLS file paths for safe stop validation.
- The plugin constructs the exact HTTPS backend URL and verifies `JARVIS_LAN_CA_CERT`; it never uses `verify=False`.

- [x] Write failing tests for parsed startup policy, exact Uvicorn arguments/recorded argv, and plugin CA-authenticated transport.
- [x] Run focused tests and confirm they fail for the expected missing behavior.
- [x] Implement explicit CLI propagation, LAN TLS args, safe process records, and plugin TLS verification.
- [x] Run focused tests and the full backend suite.

### Task 4: Documentation and end-to-end verification

**Files:**
- Modify: `README.md`
- Modify: `docs/SECURITY.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `.env.example`

- [x] Document the command, private IP discovery, CA trust on a second PC, manual firewall scope, and return to normal loopback startup.
- [x] Run `npm test` and `npm run build`.
- [x] Start the app in default mode and confirm only loopback binds.
- [x] Start LAN mode on an assigned private address, verify HTTPS health and authenticated plugin traffic with the generated CA, and confirm Hermes/Ollama remain loopback-only.
- [x] Report that remote-device access and firewall traversal are unverified unless tested from another device.
