# SmartCart 2.0 – Intelligent E-Commerce Platform

**Team:** Hack Hive  
**Institution:** Channabasaveshwara Institute of Technology (CIT), Gubbi  
**Tagline:** *Smarter Discovery. Reliable Inventory. Seamless Shopping.*

SmartCart 2.0 is an event-driven, multi-store retail e-commerce platform built on the mandatory technology stack:
- **Frontend:** React + TypeScript + Tailwind CSS v4 (Deployed on Vercel)
- **Backend:** Python + FastAPI + JWT (Deployed on Render)
- **Primary Database:** Aiven PostgreSQL (ACID transactions, row locking, transactional outbox)
- **Event Streaming:** Aiven Apache Kafka (Asynchronous decoupled consumers, outbox publisher, DLQ)
- **Search Engine:** Aiven OpenSearch (Typo-tolerant discovery, edge n-gram autocomplete, multi-store facets)

---

## Architecture Overview

1. **Transactional Integrity:** PostgreSQL ensures zero negative inventory and prevents overselling under high concurrency through row-level locking and atomic reservation functions.
2. **Transactional Outbox & Event Streaming:** Outbox pattern guarantees event publishing to Aiven Kafka without dual-write inconsistency.
3. **Intelligent Discovery:** Aiven OpenSearch delivers fuzzy matching (e.g., `bluetoth` -> `Bluetooth Headphones`) and store-aware stock availability.
4. **Multi-Store Support:** Store-wise stock across major Indian cities (Bengaluru, Mysuru, Chennai, Hyderabad, Mumbai).

---

## Project Structure

```text
SmartCart/
├── frontend/               # React + TypeScript + Tailwind CSS v4 SPA
├── backend/                # Modular FastAPI backend & Kafka workers
├── docs/                   # Architecture, specifications, and demo guides
├── .env.example            # Environment configuration template
├── .gitignore
└── README.md
```

## Quick Start (Phase 0)

### 1. Backend Setup
```bash
cd backend
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
Swagger UI will be available at: [http://localhost:8000/docs](http://localhost:8000/docs)

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Storefront will be available at: [http://localhost:5173](http://localhost:5173)
