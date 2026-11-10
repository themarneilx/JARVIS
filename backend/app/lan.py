"""Private-address validation and local HTTPS certificate management for LAN mode."""
from __future__ import annotations

import ipaddress
import os
from pathlib import Path
import shutil
import socket
import ssl
import stat
import subprocess
import tempfile


_PRIVATE_V4 = tuple(ipaddress.ip_network(value) for value in (
    '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16',
))


def normalize_private_ipv4(host: str) -> str:
    if not isinstance(host, str) or not host or host != host.strip():
        raise ValueError('LAN host must be a private IPv4 address')
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError('LAN host must be a private IPv4 address') from exc
    if not isinstance(address, ipaddress.IPv4Address) or not any(address in network for network in _PRIVATE_V4):
        raise ValueError('LAN host must be an RFC1918 private IPv4 address')
    if address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified or address.is_reserved:
        raise ValueError('LAN host must be a usable private IPv4 address')
    return str(address)


def _is_assigned(host: str) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((host, 0))
        return True
    except OSError:
        return False


def validate_lan_host(host: str) -> str:
    normalized = normalize_private_ipv4(host)
    if not _is_assigned(normalized):
        raise ValueError('LAN host must be an IPv4 address assigned to this machine')
    return normalized


def validate_start_options(lan: bool, host: str, dev: bool) -> str | None:
    if lan and dev:
        raise ValueError('HTTPS LAN mode is available only with the production frontend; omit --dev')
    if lan:
        if not host:
            raise ValueError('HTTPS LAN mode requires --lan-host with this PC’s private IPv4 address')
        return normalize_private_ipv4(host)
    if host:
        raise ValueError('--lan-host requires --lan')
    return None


def _run_openssl(arguments: list[str]) -> subprocess.CompletedProcess:
    executable = shutil.which('openssl')
    if not executable:
        raise ValueError('OpenSSL is required for HTTPS LAN mode; install the system openssl package')
    try:
        result = subprocess.run(
            [executable, *arguments], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            timeout=60, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('OpenSSL could not prepare the local HTTPS certificate') from exc
    if result.returncode:
        raise ValueError('OpenSSL could not prepare the local HTTPS certificate')
    return result


def _check_runtime_dir(path: Path) -> None:
    if path.is_symlink():
        raise ValueError('LAN certificate directories must not be symlinks')
    if not path.exists():
        path.mkdir(mode=0o700, parents=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('LAN certificate directories must be owned by this user and mode 0700')


def _check_file(path: Path, *, private: bool) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or path.is_symlink():
        raise ValueError('LAN certificate files must be regular files owned by this user')
    if private and info.st_mode & 0o077:
        raise ValueError('LAN private keys must be mode 0600')
    return True


def _new_ca(cert_dir: Path, ca_cert: Path, ca_key: Path) -> None:
    with tempfile.TemporaryDirectory(prefix='.lan-ca-', dir=cert_dir) as temporary:
        temporary_path = Path(temporary)
        staged_key = temporary_path / 'lan-ca.key'
        staged_cert = temporary_path / 'lan-ca.crt'
        _run_openssl([
            'req', '-x509', '-newkey', 'rsa:3072', '-nodes', '-sha256',
            '-keyout', str(staged_key), '-out', str(staged_cert), '-days', '3650',
            '-subj', '/CN=JARVIS Local LAN CA',
            '-addext', 'basicConstraints=critical,CA:TRUE',
            '-addext', 'keyUsage=critical,keyCertSign,cRLSign',
        ])
        staged_key.chmod(0o600)
        staged_cert.chmod(0o644)
        os.replace(staged_key, ca_key)
        os.replace(staged_cert, ca_cert)


def _server_certificate_valid(host: str, ca_cert: Path, cert: Path, key: Path) -> bool:
    if not cert.is_file() or not key.is_file():
        return False
    for arguments in (
        ['x509', '-in', str(cert), '-noout', '-checkip', host],
        ['x509', '-in', str(cert), '-noout', '-checkend', '86400'],
        ['verify', '-CAfile', str(ca_cert), str(cert)],
    ):
        try:
            _run_openssl(arguments)
        except ValueError:
            return False
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    try:
        context.load_cert_chain(str(cert), str(key))
    except (OSError, ssl.SSLError):
        return False
    return True


def _new_server_certificate(host: str, cert_dir: Path, ca_cert: Path, ca_key: Path, cert: Path, key: Path) -> None:
    with tempfile.TemporaryDirectory(prefix='.lan-server-', dir=cert_dir) as temporary:
        temporary_path = Path(temporary)
        staged_key = temporary_path / 'lan-server.key'
        csr = temporary_path / 'lan-server.csr'
        staged_cert = temporary_path / 'lan-server.crt'
        extensions = temporary_path / 'server-ext.cnf'
        extensions.write_text(
            '[server_cert]\n'
            'basicConstraints=critical,CA:FALSE\n'
            'keyUsage=critical,digitalSignature,keyEncipherment\n'
            'extendedKeyUsage=serverAuth\n'
            f'subjectAltName=IP:{host}\n',
            encoding='ascii',
        )
        _run_openssl([
            'req', '-new', '-newkey', 'rsa:2048', '-nodes', '-sha256',
            '-keyout', str(staged_key), '-out', str(csr),
            '-subj', f'/CN={host}', '-addext', f'subjectAltName=IP:{host}',
        ])
        _run_openssl([
            'x509', '-req', '-in', str(csr), '-CA', str(ca_cert),
            '-CAkey', str(ca_key), '-CAcreateserial', '-CAserial', str(temporary_path / 'ca.srl'),
            '-out', str(staged_cert), '-days', '397', '-sha256',
            '-extfile', str(extensions), '-extensions', 'server_cert',
        ])
        if _run_openssl(['verify', '-CAfile', str(ca_cert), str(staged_cert)]).returncode:
            raise ValueError('Generated LAN certificate did not verify against its local CA')
        if _run_openssl(['x509', '-in', str(staged_cert), '-noout', '-checkip', host]).returncode:
            raise ValueError('Generated LAN certificate does not match the selected IP address')
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            context.load_cert_chain(str(staged_cert), str(staged_key))
        except (OSError, ssl.SSLError) as exc:
            raise ValueError('Generated LAN certificate and private key do not match') from exc
        staged_key.chmod(0o600)
        staged_cert.chmod(0o644)
        os.replace(staged_key, key)
        os.replace(staged_cert, cert)


def ensure_lan_certificate(host: str, state_dir: Path) -> tuple[Path, Path, Path]:
    normalized = normalize_private_ipv4(host)
    state_dir = Path(state_dir)
    if state_dir.is_symlink():
        raise ValueError('LAN certificate state directory must not be a symlink')
    _check_runtime_dir(state_dir)
    cert_dir = state_dir / 'certs'
    _check_runtime_dir(cert_dir)

    ca_cert = cert_dir / 'lan-ca.crt'
    ca_key = cert_dir / 'lan-ca.key'
    cert = cert_dir / 'lan-server.crt'
    key = cert_dir / 'lan-server.key'

    ca_cert_exists = _check_file(ca_cert, private=False)
    ca_key_exists = _check_file(ca_key, private=True)
    if ca_cert_exists != ca_key_exists:
        raise ValueError('LAN CA certificate and private key are incomplete; inspect .runtime/certs')
    if not ca_cert_exists:
        _new_ca(cert_dir, ca_cert, ca_key)
    ca_key.chmod(0o600)
    ca_cert.chmod(0o644)

    cert_exists = _check_file(cert, private=False)
    key_exists = _check_file(key, private=True)
    if cert_exists and key_exists and _server_certificate_valid(normalized, ca_cert, cert, key):
        return ca_cert, cert, key

    _new_server_certificate(normalized, cert_dir, ca_cert, ca_key, cert, key)
    key.chmod(0o600)
    cert.chmod(0o644)
    ca_key.chmod(0o600)
    ca_cert.chmod(0o644)
    return ca_cert, cert, key
