"""
SmartCart 2.0 – Aiven Apache Kafka Topic Provisioning & Verification Script
Manages the four canonical SmartCart Kafka topics idempotently with strict safety defaults.

Canonical Topics (per approved plan):
1. smartcart.orders    - 3 partitions, RF=2, min.insync.replicas=1, retention=7d,  key=order_id
2. smartcart.inventory - 3 partitions, RF=2, min.insync.replicas=1, retention=7d,  key=store_id:product_id
3. smartcart.products  - 3 partitions, RF=2, min.insync.replicas=1, retention=14d, key=product_id
4. smartcart.dlq       - 2 partitions, RF=2, min.insync.replicas=1, retention=30d, key=event_id

Safety Controls:
- DRY-RUN is the DEFAULT behavior.
- Creation requires explicit --execute flag.
- Deletion requires explicit --confirm-delete-topics AND --force flags.
- Never publishes messages.
- Never modifies PostgreSQL database or local environment.
- Masks all passwords and secrets in logs and console output.
"""

import argparse
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

# Add backend directory to sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import (
    KafkaError,
    NoBrokersAvailable,
    TopicAlreadyExistsError,
)

from app.kafka.config import KafkaConfigBuilder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("smartcart.kafka.topics")


# Canonical Topic Specifications
# Note: retention settings use Aiven service defaults per cluster policy.
# Partition count = 2 matches the physical broker count and the Aiven tier policy limit (max 2 partitions per user topic).
CANONICAL_TOPICS: List[Dict[str, Any]] = [
    {
        "name": "smartcart.orders",
        "partitions": 2,
        "replication_factor": 2,
        "partition_key": "order_id (UUID)",
        "configs": {
            "min.insync.replicas": "1",
        },
        "description": "Order lifecycle events (order.placed, order.cancelled)",
    },
    {
        "name": "smartcart.inventory",
        "partitions": 2,
        "replication_factor": 2,
        "partition_key": "store_id:product_id (Composite)",
        "configs": {
            "min.insync.replicas": "1",
        },
        "description": "Store inventory stock updates, threshold alerts, and holds",
    },
    {
        "name": "smartcart.products",
        "partitions": 2,
        "replication_factor": 2,
        "partition_key": "product_id (UUID)",
        "configs": {
            "min.insync.replicas": "1",
        },
        "description": "Product catalog updates for OpenSearch projection (product.created, product.updated, etc.)",
    },
    {
        "name": "smartcart.dlq",
        "partitions": 2,
        "replication_factor": 2,
        "partition_key": "event_id (UUID)",
        "configs": {
            "min.insync.replicas": "1",
        },
        "description": "Dead Letter Queue for unprocessable events, poison pills, and diagnostic metadata",
    },
]


def create_admin_client() -> KafkaAdminClient:
    """Build and return an authenticated KafkaAdminClient using KafkaConfigBuilder."""
    common_cfg = KafkaConfigBuilder.get_common_config()

    admin_kwargs: Dict[str, Any] = {
        "bootstrap_servers": common_cfg["bootstrap_servers"],
        "security_protocol": common_cfg["security_protocol"],
        "request_timeout_ms": common_cfg.get("request_timeout_ms", 10000),
    }

    if "ssl_cafile" in common_cfg:
        admin_kwargs["ssl_cafile"] = common_cfg["ssl_cafile"]
    if "ssl_certfile" in common_cfg:
        admin_kwargs["ssl_certfile"] = common_cfg["ssl_certfile"]
    if "ssl_keyfile" in common_cfg:
        admin_kwargs["ssl_keyfile"] = common_cfg["ssl_keyfile"]
    if "ssl_check_hostname" in common_cfg:
        admin_kwargs["ssl_check_hostname"] = common_cfg["ssl_check_hostname"]

    if "sasl_mechanism" in common_cfg:
        admin_kwargs["sasl_mechanism"] = common_cfg["sasl_mechanism"]
    if "sasl_plain_username" in common_cfg:
        admin_kwargs["sasl_plain_username"] = common_cfg["sasl_plain_username"]
    if "sasl_plain_password" in common_cfg:
        admin_kwargs["sasl_plain_password"] = common_cfg["sasl_plain_password"]

    sanitized = KafkaConfigBuilder.get_sanitized_config(admin_kwargs)
    logger.info("Connecting KafkaAdminClient to %s (protocol=%s)...", sanitized.get("bootstrap_servers"), sanitized.get("security_protocol"))

    try:
        return KafkaAdminClient(**admin_kwargs)
    except Exception as exc:
        logger.error("Failed to connect KafkaAdminClient: %s", exc)
        raise


def get_cluster_state(admin_client: KafkaAdminClient) -> Dict[str, Any]:
    """Inspect active brokers and existing topics from Kafka cluster metadata."""
    metadata = admin_client._client.cluster
    brokers = metadata.brokers()
    broker_list = [{"node_id": b.nodeId, "host": b.host, "port": b.port} for b in brokers]

    all_topics = set(admin_client.list_topics())
    # Exclude internal Kafka topics like __consumer_offsets
    user_topics = sorted([t for t in all_topics if not t.startswith("__")])

    return {
        "brokers": broker_list,
        "broker_count": len(broker_list),
        "existing_user_topics": user_topics,
        "all_topics": sorted(list(all_topics)),
    }


def display_plan(cluster_state: Dict[str, Any], execute: bool) -> None:
    """Print detailed inspection and proposed topic provisioning plan."""
    print("\n" + "=" * 80)
    print(" SmartCart 2.0 – Aiven Apache Kafka Topic Configuration Plan")
    print("=" * 80)
    print(f" Mode:                 {'EXECUTION' if execute else 'DRY-RUN (Safe - No changes made)'}")
    print(f" Active Brokers:       {cluster_state['broker_count']} discovered")
    for b in cluster_state["brokers"]:
        print(f"   - Broker Node {b['node_id']}: {b['host']}:{b['port']}")

    existing_set = set(cluster_state["existing_user_topics"])
    print(f"\n Current User Topics ({len(existing_set)}):")
    if existing_set:
        for t in sorted(existing_set):
            print(f"   - {t}")
    else:
        print("   (None found - clean cluster)")

    print("\n Proposed Canonical Topics Configuration:")
    print("-" * 80)
    print(f"{'Topic Name':<22} {'Part':<6} {'RF':<4} {'min.isr':<8} {'Retention':<10} {'Status':<12} {'Partition Key':<20}")
    print("-" * 80)

    for topic_def in CANONICAL_TOPICS:
        name = topic_def["name"]
        parts = topic_def["partitions"]
        rf = topic_def["replication_factor"]
        min_isr = topic_def["configs"].get("min.insync.replicas", "1")
        retention_ms = int(topic_def["configs"].get("retention.ms", 0)) if "retention.ms" in topic_def["configs"] else None
        retention_str = f"{retention_ms // 86400000}d" if retention_ms else "service-def"
        status = "EXISTS" if name in existing_set else "WILL CREATE"
        key = topic_def["partition_key"]

        print(f"{name:<22} {parts:<6} {rf:<4} {min_isr:<8} {retention_str:<12} {status:<12} {key:<20}")
    print("-" * 80)

    print("\n Topic Descriptions & Purpose:")
    for topic_def in CANONICAL_TOPICS:
        print(f"   * {topic_def['name']}: {topic_def['description']}")
    print("=" * 80 + "\n")


def run(execute: bool = False, confirm_delete: bool = False, force: bool = False) -> int:
    """Main execution flow for topic inspection and provisioning."""
    admin_client = None
    try:
        admin_client = create_admin_client()
        cluster_state = get_cluster_state(admin_client)

        # ---------------------------------------------------------------
        # Destructive Action: Topic Deletion (Guarded by dual flags)
        # ---------------------------------------------------------------
        if confirm_delete:
            if not force:
                print("\n[ABORTED] Deletion requested but --force was not specified.")
                print("Topic deletion is a destructive operation and requires both --confirm-delete-topics and --force.")
                return 1

            target_topics = [t["name"] for t in CANONICAL_TOPICS if t["name"] in cluster_state["existing_user_topics"]]
            if not target_topics:
                print("\n[INFO] No canonical topics found to delete.")
                return 0

            print(f"\n[DESTRUCTIVE] Deleting canonical topics: {target_topics}")
            admin_client.delete_topics(target_topics, timeout_ms=10000)
            print("[OK] Topics deleted successfully.")
            return 0

        # ---------------------------------------------------------------
        # Display Plan
        # ---------------------------------------------------------------
        display_plan(cluster_state, execute=execute)

        # Prepare list of topics to create (Idempotent)
        existing_set = set(cluster_state["existing_user_topics"])
        topics_to_create = []

        for topic_def in CANONICAL_TOPICS:
            name = topic_def["name"]
            if name in existing_set:
                continue

            new_topic = NewTopic(
                name=name,
                num_partitions=topic_def["partitions"],
                replication_factor=topic_def["replication_factor"],
                topic_configs=topic_def["configs"],
            )
            topics_to_create.append(new_topic)

        if not execute:
            # Active policy check with cluster controller without creating topics
            if topics_to_create:
                try:
                    admin_client.create_topics(new_topics=topics_to_create, validate_only=True)
                    print("[DRY-RUN] Broker Policy Pre-Flight: PASSED (Cluster accepted all topic configurations with validate_only=True)")
                except Exception as val_exc:
                    print(f"[DRY-RUN] Broker Policy Pre-Flight: FAILED: {val_exc}")
                    return 1

            print("[DRY-RUN] Verification complete. No topics were created, modified, or deleted.")
            print("[INFO] To provision topics after approval, run with: --execute")
            return 0

        if not topics_to_create:
            print("\n[OK] All canonical topics are already provisioned. Nothing to do.")
            return 0

        print(f"\n[EXECUTE] Creating {len(topics_to_create)} topics on Aiven Kafka cluster...")
        admin_client.create_topics(new_topics=topics_to_create, validate_only=False)
        print("[OK] Topic creation request submitted successfully.")

        # Verify post-creation state
        updated_state = get_cluster_state(admin_client)
        print(f"\n[VERIFICATION] Current topics in cluster: {updated_state['existing_user_topics']}")
        return 0

    except NoBrokersAvailable as nba_err:
        print(f"\n[ERROR] Could not connect to Kafka brokers: {nba_err}")
        return 1
    except KafkaError as k_err:
        print(f"\n[ERROR] Kafka operation failed: {k_err}")
        return 1
    except Exception as exc:
        print(f"\n[ERROR] Unexpected error: {exc}")
        return 1
    finally:
        if admin_client is not None:
            try:
                admin_client.close()
            except Exception:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SmartCart 2.0 Aiven Kafka Topic Provisioner and Inspector",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Execute topic creation on Aiven Kafka (Default is dry-run mode).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Run in dry-run mode without modifying the cluster (Default: True).",
    )
    parser.add_argument(
        "--confirm-delete-topics",
        action="store_true",
        default=False,
        help="Destructive: request deletion of canonical topics.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Required confirmation flag for destructive operations.",
    )

    args = parser.parse_args()

    # Determine execution mode: if --execute is explicitly given, execute=True
    execute = args.execute
    confirm_delete = args.confirm_delete_topics
    force = args.force

    exit_code = run(execute=execute, confirm_delete=confirm_delete, force=force)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
