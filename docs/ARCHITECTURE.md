# SmartCart 2.0 – Architecture Specification

## Overview
SmartCart 2.0 is an enterprise-grade multi-store e-commerce architecture designed to address inventory drift, brittle product discovery, and tightly coupled order pipelines.

## Architectural Boundaries

1. **Transactional Domain (Aiven PostgreSQL):**
   - Tables: `stores`, `products`, `customers`, `orders`, `order_items`, `inventory`, `reservations`, `idempotency_keys`, `order_status_history`, `inventory_audit_log`, `outbox_events`, `processed_events`.
   - Invariant: `available_stock >= 0`. No two users can reserve the last remaining item.
   - 10-minute automated reservation hold window.

2. **Event Backbone (Aiven Apache Kafka):**
   - Asynchronous decoupled processing via Transactional Outbox.
   - Topics:
     - `order.placed`
     - `order.cancelled`
     - `inventory.changed`
     - `product.changed`
     - `search.events`
     - `order.placed.dlq`
   - Independent idempotent consumers:
     - Search Indexer
     - Notifications
     - Analytics
     - Inventory Projection
     - Low-Stock Alerts

3. **Intelligent Discovery (Aiven OpenSearch):**
   - Typo tolerance with `fuzziness: "AUTO"`.
   - Edge n-gram tokenization for instant autocomplete suggestions.
   - Indian synonym mapping (e.g. *chawal -> rice*, *doodh -> milk*, *atta -> wheat flour*, *mobile -> phone*).
   - Real-time store availability filtering.
