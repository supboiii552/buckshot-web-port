#!/usr/bin/env python3
"""Generate a self-signed TLS certificate for serving the web build over HTTPS.

iOS Safari requires a secure context before it will grant SharedArrayBuffer,
and Godot's threaded web build needs SharedArrayBuffer - so the iPad can only
load the game from https://<this-pc>:8124/ . Browsers do not trust self-signed
certificates, so the first visit shows a warning the player accepts once.

    python webport/tools/make_cert.py
"""
import datetime
import ipaddress
import os
import socket
import ssl  # noqa: F401  (kept so the failure mode is obvious if TLS is broken)

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
except ImportError:
    raise SystemExit("the 'cryptography' package is required: pip install cryptography")

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "certs")


def lan_ip():
    """Best-effort: the address the iPad will actually reach this PC on."""
    # 1) the address the OS would route to the internet through
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if not ip.startswith("169.254."):
                return ip
        finally:
            s.close()
    except OSError:
        pass
    # 2) any private-range address on this host
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith(("192.168.", "10.", "172.")) and not ip.startswith("169.254."):
                return ip
    except OSError:
        pass
    return "127.0.0.1"


def main():
    os.makedirs(OUT, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ip = lan_ip()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Buckshot Roulette Web Port")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                x509.IPAddress(ipaddress.ip_address(ip)),
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    with open(os.path.join(OUT, "server.pem"), "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(os.path.join(OUT, "server.key"), "wb") as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ))
    print(f"wrote self-signed cert for {ip} (10 years) into {os.path.abspath(OUT)}")
    print("serve with:  python webport/tools/serve_web.py 8124 --https")


if __name__ == "__main__":
    main()
