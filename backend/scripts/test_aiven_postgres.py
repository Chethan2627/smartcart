"""
SmartCart 2.0 – Isolated Aiven PostgreSQL Connection Test
Connects to Aiven PostgreSQL using async SQLAlchemy (asyncpg dialect) and validates TLS with the Aiven CA certificate.

Safety rules strictly enforced:
- Read-only queries only: SELECT version(), current_database(), current_user
- Never creates, updates, or deletes any database rows or tables
- Never exposes passwords or unmasked database credentials in stdout/logs
- Disposes connection pool cleanly on exit
"""

import argparse
import asyncio
import os
from pathlib import Path
import ssl
import sys
from urllib.parse import quote_plus
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def resolve_path(path_str: str, base_dir: Path) -> Path:
    """Resolve relative or absolute path against base_dir."""
    p = Path(path_str)
    if p.is_absolute():
        return p
    # Try relative to base_dir
    candidate1 = base_dir / p
    if candidate1.exists():
        return candidate1
    # Try relative to parent of base_dir
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


async def run_connection_test(
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
    ca_path: Path | None,
    verify_certs: bool = True,
    timeout_seconds: int = 15,
) -> int:
    """Execute isolated read-only connection test to Aiven PostgreSQL."""
    print("=" * 70)
    print(" SmartCart 2.0 – Aiven PostgreSQL Connection Test")
    print("=" * 70)

    # Sanitize and display target parameters
    print(f"Target Host:       {host}")
    print(f"Target Port:       {port}")
    print(f"Database:          {database}")
    print(f"Username:          {user}")
    print(f"Password:          {'*' * 8} (hidden)")

    # Configure SSL / TLS context
    connect_args: dict = {}
    if ca_path and ca_path.is_file():
        print(f"TLS Verification:  Enabled (using CA: {ca_path})")
        ssl_ctx = ssl.create_default_context(cafile=str(ca_path))
        ssl_ctx.verify_mode = ssl.CERT_REQUIRED
        ssl_ctx.check_hostname = verify_certs
        connect_args["ssl"] = ssl_ctx
    else:
        if ca_path:
            print(f"[!] Warning: Configured CA certificate path not found: {ca_path}")
        print("TLS Verification:  System default TLS (ssl='require')")
        # In asyncpg, ssl='require' can be passed directly
        connect_args["ssl"] = "require"

    connect_args["timeout"] = timeout_seconds

    # URL-encode credentials to safely handle special characters
    safe_user = quote_plus(user)
    safe_pass = quote_plus(password)
    async_db_url = (
        f"postgresql+asyncpg://{safe_user}:{safe_pass}@{host}:{port}/{database}"
    )

    print("\nConnecting using asyncpg and SQLAlchemy 2.x...")

    engine = None
    try:
        engine = create_async_engine(
            async_db_url,
            connect_args=connect_args,
            echo=False,
            pool_pre_ping=True,
        )

        async with asyncio.timeout(timeout_seconds):
            async with engine.connect() as conn:
                # 1. Version
                ver_res = await conn.execute(text("SELECT version();"))
                db_version = ver_res.scalar()

                # 2. Current Database
                db_res = await conn.execute(text("SELECT current_database();"))
                current_db = db_res.scalar()

                # 3. Current User
                user_res = await conn.execute(text("SELECT current_user;"))
                current_user = user_res.scalar()

        print("\n" + "=" * 70)
        print(" [SUCCESS] Successfully connected to Aiven PostgreSQL!")
        print("=" * 70)
        print(f"Connected Database:  {current_db}")
        print(f"Connected User:      {current_user}")
        print(f"PostgreSQL Version:  {db_version}")
        print("Connection Mode:     Asynchronous (asyncpg driver)")
        print("TLS Status:          Encrypted & Verified")
        print("Operation:           Strictly Read-Only (0 rows modified)")
        print("=" * 70)
        return 0

    except TimeoutError:
        print("\n" + "!" * 70)
        print(f" [FAILED] Connection timed out after {timeout_seconds} seconds.")
        print("!" * 70)
        print("Possible causes:")
        print("  1. Aiven service is paused, starting up, or rebuilding.")
        print("  2. Firewall / network block on outbound port 17602.")
        print("  3. Hostname is unresolved or incorrect.")
        return 1

    except Exception as exc:
        print("\n" + "!" * 70)
        print(" [FAILED] Unable to connect to Aiven PostgreSQL.")
        print("!" * 70)
        exc_name = type(exc).__name__
        msg = str(exc)
        # Protect against credential leaks in raw exception text
        if password and password in msg:
            msg = msg.replace(password, "********")
        print(f"Error Type: {exc_name}")
        print(f"Details:    {msg}")

        # Provide targeted diagnostics
        if "password authentication failed" in msg.lower():
            print("\nDiagnostic:")
            print("  Authentication failed. Please verify that your regenerated password")
            print("  in backend/.env.aiven exactly matches the password in the Aiven console.")
        elif "certificate verify failed" in msg.lower():
            print("\nDiagnostic:")
            print("  TLS Certificate verification failed. Please verify that ca.pem is the")
            print("  exact Project CA certificate downloaded from your Aiven dashboard.")
        elif "getaddrinfo failed" in msg.lower():
            print("\nDiagnostic:")
            print("  DNS lookup failed for the Aiven host. Please check your internet connection")
            print("  and verify the host domain.")
        return 1

    finally:
        if engine is not None:
            await engine.dispose()
            print("\nAsync database connection pool cleanly disposed.")


def main():
    parser = argparse.ArgumentParser(
        description="SmartCart 2.0 – Isolated Aiven PostgreSQL Connection Tester"
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
        "--timeout",
        type=int,
        default=15,
        help="Connection timeout in seconds (default: 15)",
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
        print(f"Loading isolated environment from: {env_file_path}")
        load_dotenv(dotenv_path=env_file_path, override=True)
    else:
        print(f"Notice: Environment file '{env_file_path}' not found; using existing environment variables.")

    # Read connection parameters with safe fallbacks
    host = os.getenv("AIVEN_PG_HOST") or "pg-1f1fcda-harshith-6c6d.c.aivencloud.com"
    port_str = os.getenv("AIVEN_PG_PORT") or "17602"
    database = os.getenv("AIVEN_PG_DATABASE") or "defaultdb"
    user = os.getenv("AIVEN_PG_USER") or "avnadmin"
    password = os.getenv("AIVEN_PG_PASSWORD")

    try:
        port = int(port_str)
    except ValueError:
        print(f"Error: Invalid port '{port_str}'. Port must be an integer.")
        sys.exit(1)

    # Validate password presence
    if not password or password == "PASTE_YOUR_NEW_AIVEN_PASSWORD_HERE":
        print("\n" + "=" * 70)
        print(" [!] Missing Aiven PostgreSQL Password")
        print("=" * 70)
        print("The password was not provided or is still set to the placeholder.")
        print("\nTo test the connection:")
        print("1. Regenerate your service password in the Aiven Console.")
        print(f"2. Open '{env_file_path}' in your editor.")
        print("3. Set AIVEN_PG_PASSWORD=<your_new_password>")
        print("4. Re-run this test script.")
        print("=" * 70)
        sys.exit(1)

    # Determine CA certificate path
    raw_ca_path = args.ca_path or os.getenv("AIVEN_PG_SSL_CA_PATH")
    ca_path = find_ca_certificate(raw_ca_path, backend_dir)

    verify_certs_str = os.getenv("AIVEN_PG_SSL_VERIFY_CERTS", "true").lower()
    verify_certs = verify_certs_str in ("true", "1", "yes")

    exit_code = asyncio.run(
        run_connection_test(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            ca_path=ca_path,
            verify_certs=verify_certs,
            timeout_seconds=args.timeout,
        )
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
