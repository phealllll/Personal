# ADR-001: Cryptographic Non-Repudiation and Vault Segregation for OT Telemetry

## Status
Accepted

## Context
In industrial IoT environments, operational telemetry data feeds safety-critical analytics (e.g., compressor vibration and temperature anomalies). Ingesting raw CSV payloads directly into an analytical warehouse without validation opens the system to data tampering, spoofing, and man-in-the-middle attacks. 

## Decision
We implemented a **Zero-Trust Ingestion Pipeline** enforcing two major security controls:
1. **Cryptographic Payload Signing:** Every emitted batch is cryptographically signed using **HMAC-SHA256** with constant-time verification (`hmac.compare_digest`) to prevent timing attacks and unauthorized modifications.
2. **Asset Isolation (Segregation of Duties):** Initial implementations stored sidecar `.hmac` files in the exact same directory as the raw CSVs. To eliminate the CWE-434 file-tampering vulnerability (where an attacker with folder write access could modify a payload and recompute a fake sidecar next to it), we decoupled storage into two distinct vaults:
   - `data/`: Append-only raw telemetry payload storage.
   - `signatures/`: Strictly isolated cryptographic signature storage.

## Consequences
- **Positive:** Guarantees complete non-repudiation. Any unauthorized modification to a historical CSV batch is instantly intercepted, rejected, and logged as an audit failure in DuckDB without polluting the analytical warehouse.
- **Negative:** Adds minor file-system dependency checks and strict directory structuring requirements for deployment.
