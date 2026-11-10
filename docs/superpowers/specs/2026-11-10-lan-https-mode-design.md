# J.A.R.V.I.S. HTTPS LAN Mode

## Intent

Allow an explicitly started J.A.R.V.I.S. instance to be used from another
computer on the user's private network, including its authenticated desktop
controls, while keeping ordinary `npm start` on loopback.

## Approaches

- **SSH tunnel:** available without changing the app's bind address, but requires
  SSH access and is less convenient for browser microphone permissions.
- **Plain HTTP on `0.0.0.0`:** rejected because it listens on every interface and
  sends browser sessions without transport encryption.
- **Opt-in HTTPS on one private address:** selected. `npm start -- --lan
  --lan-host <private-ip>` binds only that assigned RFC1918 IPv4 address, with
  an app-local CA and a server certificate containing that IP as a SAN.

## Design

LAN mode is a separate production startup path. It requires an assigned private
IPv4 address, validates that it is neither loopback nor public, and refuses
wildcard binds. Startup creates private CA/server key material under ignored
`.runtime/certs/`, and prints the HTTPS URL and public CA certificate path. The
remote browser must trust that CA certificate. The CA private key never leaves
the J.A.R.V.I.S. host.

The backend accepts only the exact HTTPS origin and Host for the chosen address,
sets `Secure`, `HttpOnly`, `SameSite=Strict` session cookies, and serves TLS
directly. The reviewed Hermes plugin reaches the same listener over HTTPS using
the generated CA; its bearer remains required for `/api/internal`. Hermes and
Ollama stay bound to loopback. Normal startup remains loopback-only. No firewall,
router, system trust store, startup service, or global Hermes configuration is
changed.

LAN mode requires OpenSSL on the host. The browser-device trust step and a
manual, LAN-scoped firewall rule are documented; the application does not open
ports in the firewall. An existing pairing token is not printed to browser
responses, and no bearer credentials enter frontend assets.

## Constraints and non-goals

- No wildcard listener, public routing, hosted inference, or automatic firewall
  mutation.
- Only an explicit private IPv4 address can be selected.
- The HTTPS listener uses the existing backend port; the Hermes API and Ollama
  remain loopback-only.
- LAN access is opt-in for each launch and is not enabled by default.
- The mode does not install the CA on other devices or guarantee that their
  firewall permits the connection.

## Acceptance

- Default launch binds the backend only to `127.0.0.1`.
- LAN launch requires an assigned private IPv4 address, TLS certificate/key,
  exact HTTPS Host/Origin checks, and a Secure session cookie.
- Public, loopback, link-local, unspecified, malformed, and wildcard addresses
  are refused.
- Hermes plugin traffic verifies the local CA and continues to authenticate;
  missing or invalid certificates fail closed.
- Tests verify the startup command, security boundaries, certificate SAN, and
  local HTTPS health/login flow without claiming that a remote device has been
  tested.
