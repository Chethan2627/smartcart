import os
import sys
import time
from pathlib import Path
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv


def get_db_url():
    root_dir = Path(__file__).resolve().parent.parent.parent
    load_dotenv(root_dir / ".env")
    load_dotenv(root_dir / "backend" / ".env")

    url = os.getenv("DATABASE_SYNC_URL") or os.getenv("DATABASE_URL")
    if not url:
        return None
    # Normalize asyncpg scheme to standard postgresql scheme for psycopg2
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


def execute_sql_file(conn, file_path):
    print(f"\n=======================================================")
    print(f"Executing: {file_path.name}")
    print(f"=======================================================")
    start_time = time.time()

    with open(file_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    with conn.cursor() as cur:
        try:
            cur.execute(sql_content)
            if cur.description:
                rows = cur.fetchall()
                colnames = [desc[0] for desc in cur.description]
                print("\n[RESULT TABLE] Query Output:")
                print(" | ".join(colnames))
                print("-" * 70)
                for row in rows:
                    print(" | ".join(str(val) for val in row))
        except psycopg2.Error as e:
            print(f"\n[ERROR] Execution failed on {file_path.name}:")
            print(f"  SQLSTATE Code: {e.pgcode}")
            print(f"  Error Message: {e.pgerror or str(e)}")
            if hasattr(e, "diag") and e.diag:
                print(f"  Message Primary: {e.diag.message_primary}")
                print(f"  Message Detail:  {e.diag.message_detail}")
                print(f"  Context:         {e.diag.context}")
            raise

    elapsed = time.time() - start_time
    print(f"\n[SUCCESS] Completed {file_path.name} in {elapsed:.2f}s")

    # Display any notices accumulated during execution (e.g. self-test assertions notice)
    if conn.notices:
        print("\n[POSTGRESQL NOTICES]:")
        for notice in conn.notices:
            print("  " + notice.strip())
        del conn.notices[:]


def main():
    db_url = get_db_url()
    if not db_url:
        print("[ERROR] DATABASE_URL or DATABASE_SYNC_URL is not configured.")
        print("Please configure DATABASE_URL in your .env file or environment.")
        sys.exit(1)

    # Mask credentials for terminal output
    safe_display = db_url.split("@")[-1] if "@" in db_url else "database"
    print(f"Target development database host/db: {safe_display}")
    print("Connecting to PostgreSQL development database...")

    try:
        conn = psycopg2.connect(db_url)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        print("[CONNECTED] Database connection established successfully.")
        with conn.cursor() as cur:
            print("[CLEAN] Resetting public schema to guarantee pristine clean state...")
            cur.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
    except Exception as e:
        print(f"[FAILED] Could not connect to PostgreSQL database: {e}")
        sys.exit(1)

    root_dir = Path(__file__).resolve().parent.parent.parent
    schema_file = root_dir / "database" / "01_schema.sql"
    test_file = root_dir / "database" / "02_seed_and_test.sql"

    try:
        execute_sql_file(conn, schema_file)
        execute_sql_file(conn, test_file)
        print("\n=======================================================")
        print("[ALL TESTS PASSED] Controlled Phase 1 validation successful.")
        print("All self-tests passed and initial inventory baselines verified.")
        print("=======================================================")
    except Exception:
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
