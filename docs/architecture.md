# Nova Industrial IoT Telemetry Pipeline: Architecture Overview

## Overview
The Nova Industrial Pipeline is a production-grade, secure data engineering framework designed to ingest, verify, and store operational telemetry (OT) for the K-101 compressor train. It bridges high-speed data engineering (DuckDB) with rigorous cybersecurity controls (HMAC-SHA256, RBAC, asset isolation).

## System Architecture: Medallion Pattern
The pipeline follows a structured Medallion architecture:
- **Bronze Layer (`data/`):** Append-only vault storing raw, immutable CSV operational batches generated daily.
- **Cryptographic Vault (`signatures/`):** Isolated directory storing HMAC-SHA256 signature sidecars, decoupled from the raw payloads to ensure defense-in-depth.
- **Silver Layer (`nova_warehouse.duckdb`):** High-performance, serverless OLAP data warehouse powered by DuckDB for fast analytical aggregations, schema validation, and audit logging.
- **Application/Presentation Layer (Planned):** Streamlit interactive UI featuring role-based access control (RBAC) security wrappers.
