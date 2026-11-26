"""A private certificate authority for the stack's HTTPS-only service addresses.

Production's Cloud Run services are reached over HTTPS, and the code checks it:
the batch worker's control-plane address, the recovery task audience and the
enrichment handler are refused unless their scheme is ``https``. Rather than
lift those checks, a prod-parity stack serves its Cloud Run stand-ins
over real TLS on loopback, with a certificate from an authority that exists
only in this stack's state directory.

``bundle`` is the public roots (certifi) plus that authority, so one trust file
serves both local service calls and the real provider APIs.
"""

from __future__ import annotations

import datetime
import ipaddress
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LocalTls:
    certificate: Path
    key: Path
    bundle: Path


def ensure(directory: Path) -> LocalTls:
    """Create the authority and loopback certificate once; reuse them afterwards."""
    tls = LocalTls(directory / "server.pem", directory / "server.key", directory / "trust-bundle.pem")
    if tls.certificate.is_file() and tls.key.is_file() and tls.bundle.is_file():
        return tls
    import certifi
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc)

    def name(common: str) -> x509.Name:
        return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common)])

    authority_key = ec.generate_private_key(ec.SECP256R1())
    authority = (
        x509.CertificateBuilder()
        .subject_name(name("Omi dev harness local authority"))
        .issuer_name(name("Omi dev harness local authority"))
        .public_key(authority_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=825))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(authority_key, hashes.SHA256())
    )
    server_key = ec.generate_private_key(ec.SECP256R1())
    server = (
        x509.CertificateBuilder()
        .subject_name(name("127.0.0.1"))
        .issuer_name(authority.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=397))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1")), x509.DNSName("localhost")]),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(authority_key, hashes.SHA256())
    )
    pem = serialization.Encoding.PEM
    tls.key.write_bytes(server_key.private_bytes(pem, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    tls.key.chmod(0o600)
    tls.certificate.write_bytes(server.public_bytes(pem))
    # The authority's key is discarded: nothing else can ever be issued under it.
    tls.bundle.write_bytes(Path(certifi.where()).read_bytes() + b"\n" + authority.public_bytes(pem))
    return tls
