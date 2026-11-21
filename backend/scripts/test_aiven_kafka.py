"""
SmartCart 2.0 – Isolated Aiven Apache Kafka Connection Test
Performs non-destructive broker reachability, TLS CA verification, SASL authentication,
and cluster metadata inspection.

Strict Safety Rules:
- Never produces or consumes messages
- Never creates, alters, or deletes topics
- Never modifies broker configuration
- Never leaks passwords or secrets to logs or terminal
- Disposes client connections cleanly on exit
"""

import argparse
import os
from pathlib import Path
import socket
import ssl
import sys
from dotenv import load_dotenv

from kafka import KafkaAdminClient
from kafka.errors import (
    AuthenticationFailedError,
    NoBrokersAvailable,
    UnsupportedSaslMechanismError,
)


def resolve_path(path_str: str, base_dir: Path) -> Path:
    """Resolve relative or absolute path against base_dir."""
    p = Path(path_str)
    if p.is_absolute():
        return p
    candidate1 = base_dir / p
    if candidate1.exists():
        return candidate1
    candidate2 = base_dir.parent / p
    if candidate2.exists():
        return candidate2
    return candidate1


def find_ca_certificate(configured_path: str | None, backend_dir: Path) -> Path | None:
    """Search for ca.pem in common project locations."""
    search_locations = []
    if configured_path:
        search_locations.append(resolve_path(configured_path, backend_dir))

    search_locations.extend([
        backend_dir / "certs" / "ca.pem",
        backend_dir.parent / "certs" / "ca.pem",
        backend_dir / "ca.pem",
        backend_dir.parent / "ca.pem",
    ])

    for loc in search_locations:
        if loc.is_file():
            return loc.resolve()
    return None


def test_tcp_reachability(host: str, port: int, timeout: float = 5.0) -> bool:
    """Validate raw TCP socket connection to Kafka broker port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return True
    finally:
        s.close()


def test_tls_handshake(host: str, port: int, ca_path: Path, timeout: float = 5.0) -> dict:
    """Validate TLS handshake and extract server certificate metadata."""
    ctx = ssl.create_default_context(cafile=str(ca_path))
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.check_hostname = True

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    with ctx.wrap_socket(s, server_hostname=host) as ss:
        ss.connect((host, port))
        cert = ss.getpeercert()
        return {
            "subject": dict(x[0] for x in cert.get("subject", ())),
            "issuer": dict(x[0] for x in cert.get("issuer", ())),
            "version": cert.get("version"),
        }


def run_kafka_test(
    bootstrap_servers: str,
    host: str,
    port: int,
    username: str,
    password: str,
    sasl_mechanism: str,
    security_protocol: str,
    ca_path: Path,
    timeout_seconds: int = 10,
) -> int:
    print("=" * 75)
    print(" SmartCart 2.0 – Aiven Apache Kafka Connection & Metadata Test")
    print("=" * 75)
    print(f"Target Bootstrap:  {bootstrap_servers}")
    print(f"Security Protocol: {security_protocol}")
    print(f"SASL Mechanism:    {sasl_mechanism}")
    print(f"Username:          {username}")
    print(f"Password:          {'*' * 8} (hidden)")
    print(f"CA Certificate:    {ca_path} (Verification Enabled)")
    print("=" * 75)

    # --------------------------------------------------------------------
    # Stage 1: Raw TCP Reachability Check
    # --------------------------------------------------------------------
    print("\n[Stage 1/3] Testing raw TCP connectivity to broker port...")
    try:
        tcp_ok = test_tcp_reachability(host, port, timeout=5.0)
        if tcp_ok:
            print(f"  [OK] TCP port {port} is open and reachable on {host}.")
    except Exception as exc:
        print(f"  [!] TCP Connection FAILED: {exc}")
        print("  Diagnostic: Check firewall rules or verify the Aiven service is active.")
        return 1

    # --------------------------------------------------------------------
    # Stage 2: TLS Handshake & CA Certificate Verification Check
    # --------------------------------------------------------------------
    print("\n[Stage 2/3] Performing TLS handshake with CA certificate verification...")
    try:
        cert_info = test_tls_handshake(host, port, ca_path, timeout=5.0)
        issuer_cn = cert_info.get("issuer", {}).get("commonName", "Unknown")
        subject_cn = cert_info.get("subject", {}).get("commonName", "Unknown")
        print(f"  [OK] TLS handshake verified with CA certificate.")
        print(f"       Broker Common Name: {subject_cn}")
        print(f"       Certificate Issuer: {issuer_cn}")
    except ssl.SSLCertVerificationError as ssl_err:
        print(f"  [!] TLS Certificate Verification FAILED: {ssl_err}")
        print("  Diagnostic: The CA certificate in certs/ca.pem does not match the broker's CA.")
        return 1
    except Exception as exc:
        print(f"  [!] TLS Handshake FAILED: {exc}")
        return 1

    # --------------------------------------------------------------------
    # Stage 3: SASL Authentication & Cluster Metadata Inspection
    # --------------------------------------------------------------------
    print(f"\n[Stage 3/3] Authenticating via SASL ({sasl_mechanism}) & fetching metadata...")
    admin_client = None
    try:
        admin_client = KafkaAdminClient(
            bootstrap_servers=bootstrap_servers,
            security_protocol=security_protocol,
            sasl_mechanism=sasl_mechanism.upper(),
            sasl_plain_username=username,
            sasl_plain_password=password,
            ssl_cafile=str(ca_path),
            ssl_check_hostname=True,
            request_timeout_ms=timeout_seconds * 1000,
            api_version_auto_timeout_ms=timeout_seconds * 1000,
        )

        cluster_info = admin_client.describe_cluster()
        brokers = cluster_info.get("brokers", [])
        cluster_id = cluster_info.get("cluster_id", "N/A")
        controller_id = cluster_info.get("controller_id", "N/A")

        topics = admin_client.list_topics()

        print("\n" + "=" * 75)
        print(" [SUCCESS] Successfully authenticated and connected to Aiven Kafka!")
        print("=" * 75)
        print(f"Cluster ID:          {cluster_id}")
        print(f"Active Controller:   Node ID {controller_id}")
        print(f"Active Brokers ({len(brokers)}):")
        for b in brokers:
            node_id = b.get("node_id")
            b_host = b.get("host")
            b_port = b.get("port")
            rack = b.get("rack")
            rack_str = f" [rack: {rack}]" if rack else ""
            print(f"  - Node {node_id}: {b_host}:{b_port}{rack_str}")

        print(f"\nExisting Topics ({len(topics)}):")
        if topics:
            for t in sorted(topics):
                print(f"  - {t}")
        else:
            print("  (No user topics created yet - pristine cluster)")

        print("=" * 75)
        print("Verification Summary:")
        print("  - Network Connectivity: Verified")
        print("  - TLS & CA Verification: Verified")
        print(f"  - SASL Authentication ({sasl_mechanism}): Verified")
        print("  - Metadata Discovery: Verified")
        print("  - State Alteration: Strictly Zero (0 messages, 0 topic changes)")
        print("=" * 75)
        return 0

    except AuthenticationFailedError:
        print("\n" + "!" * 75)
        print(f" [FAILED] SASL Authentication failed with mechanism '{sasl_mechanism}'.")
        print("!" * 75)
        print("Diagnostic:")
        print("  1. Verify the password in backend/.env.aiven exactly matches your Aiven console.")
        print(f"  2. Verify that '{sasl_mechanism}' matches the mechanism configured in Aiven.")
        print("     Try running with: --mechanism SCRAM-SHA-512 or --mechanism PLAIN")
        return 1

    except UnsupportedSaslMechanismError as mech_err:
        print("\n" + "!" * 75)
        print(f" [FAILED] Unsupported SASL mechanism: {mech_err}")
        print("!" * 75)
        print(f"Diagnostic: The broker does not accept '{sasl_mechanism}'.")
        print("Try re-running with: --mechanism SCRAM-SHA-512 or --mechanism PLAIN")
        return 1

    except NoBrokersAvailable as nba_err:
        print("\n" + "!" * 75)
        print(f" [FAILED] No brokers available: {nba_err}")
        print("!" * 75)
        print("Diagnostic:")
        print("  Authentication was rejected by the broker or credentials/mechanism were invalid.")
        print(f"  Currently attempted mechanism: {sasl_mechanism}")
        print("  If your Aiven user was configured with SCRAM-SHA-512, try:")
        print("    python scripts/test_aiven_kafka.py --mechanism SCRAM-SHA-512")
        return 1

    except Exception as exc:
        print("\n" + "!" * 75)
        print(f" [FAILED] Kafka client error: {type(exc).__name__}: {exc}")
        print("!" * 75)
        return 1

    finally:
        if admin_client is not None:
            try:
                admin_client.close()
                print("\nKafka client connection cleanly closed.")
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(
        description="SmartCart 2.0 – Isolated Aiven Apache Kafka Connection Tester"
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        help="Path to custom environment file (defaults to backend/.env.aiven)",
    )
    parser.add_argument(
        "--ca-path",
        type=str,
        default=None,
        help="Path to Aiven ca.pem certificate (defaults to backend/certs/ca.pem)",
    )
    parser.add_argument(
        "--mechanism",
        type=str,
        default=None,
        help="Override SASL mechanism (e.g. SCRAM-SHA-256, SCRAM-SHA-512, PLAIN)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Timeout in seconds (default: 10)",
    )
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent.parent

    # Determine env file location
    if args.env_file:
        env_file_path = resolve_path(args.env_file, backend_dir)
    else:
        candidate_env = backend_dir / ".env.aiven"
        if candidate_env.exists():
            env_file_path = candidate_env
        else:
            env_file_path = backend_dir.parent / ".env.aiven"

    if env_file_path.exists():
        print(f"Loading isolated configuration from: {env_file_path}")
        load_dotenv(dotenv_path=env_file_path, override=True)
    else:
        print(f"Notice: Environment file '{env_file_path}' not found; using existing environment.")

    host = os.getenv("AIVEN_KAFKA_HOST", "kafka-3cda5cc1-harshith-6c6d.a.aivencloud.com")
    port_str = os.getenv("AIVEN_KAFKA_PORT", "17615")
    bootstrap = os.getenv("AIVEN_KAFKA_BOOTSTRAP_SERVERS", f"{host}:{port_str}")
    username = os.getenv("AIVEN_KAFKA_USERNAME", "avnadmin")
    password = os.getenv("AIVEN_KAFKA_PASSWORD") or os.getenv("KAFKA_SASL_PASSWORD")

    security_protocol = os.getenv("AIVEN_KAFKA_SECURITY_PROTOCOL", "SASL_SSL").upper()
    sasl_mechanism = (args.mechanism or os.getenv("AIVEN_KAFKA_SASL_MECHANISM") or "SCRAM-SHA-256").upper()

    try:
        port = int(port_str)
    except ValueError:
        print(f"Error: Invalid port '{port_str}'. Must be an integer.")
        sys.exit(1)

    # Validate password presence
    if not password or password == "PASTE_YOUR_AIVEN_KAFKA_PASSWORD_HERE":
        print("\n" + "=" * 75)
        print(" [!] Missing Aiven Apache Kafka Password")
        print("=" * 75)
        print("The Kafka password was not provided or is still set to the placeholder.")
        print("\nTo test the connection:")
        print(f"1. Open '{env_file_path}' in your text editor.")
        print("2. Set AIVEN_KAFKA_PASSWORD=<your_actual_kafka_password>")
        print("3. Re-run this test script.")
        print("=" * 75)
        sys.exit(1)

    raw_ca_path = args.ca_path or os.getenv("AIVEN_KAFKA_SSL_CA_PATH")
    ca_path = find_ca_certificate(raw_ca_path, backend_dir)
    if not ca_path or not ca_path.is_file():
        print(f"\n[!] FATAL: CA certificate not found at: {raw_ca_path or 'certs/ca.pem'}")
        print("Please ensure the Aiven Project CA certificate is placed at backend/certs/ca.pem.")
        sys.exit(1)

    exit_code = run_kafka_test(
        bootstrap_servers=bootstrap,
        host=host,
        port=port,
        username=username,
        password=password,
        sasl_mechanism=sasl_mechanism,
        security_protocol=security_protocol,
        ca_path=ca_path,
        timeout_seconds=args.timeout,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
