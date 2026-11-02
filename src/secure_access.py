from functools import wraps
from pathlib import Path
import duckdb

# Anchor paths to the project root (nova/)
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "nova_warehouse.duckdb"

# Simulated Identity & Access Management (IAM) context
CURRENT_USER_SESSION = {
    "username": "raphael_sec",
    "role": "CYBER_SECURITY_AUDITOR"  # Change to "OPERATOR" or "RELIABILITY_ENGINEER" to test
}

def require_role(allowed_roles):
    """Decorator to enforce strict Role-Based Access Control on data queries."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user_role = CURRENT_USER_SESSION.get("role")
            if user_role not in allowed_roles:
                raise PermissionError(
                    f"[SECURITY AUDIT] ACCESS DENIED: User '{CURRENT_USER_SESSION['username']}' with role '{user_role}' "
                    f"is not authorized to execute '{func.__name__}'. Required roles: {allowed_roles}"
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator


# --- Secure Data Access Layer ---

@require_role(["RELIABILITY_ENGINEER", "OPERATOR"])
def query_operational_telemetry():
    """Operators and Engineers can view live telemetry."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    results = con.execute("SELECT timestamp, temperature_c, pressure_psi FROM k101_sensor_logs LIMIT 5").fetchall()
    con.close()
    return results


@require_role(["RELIABILITY_ENGINEER", "CYBER_SECURITY_AUDITOR"])
def query_security_audit_logs():
    """Only Engineers and Security Auditors can view system audit trails and anomalies."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    results = con.execute("SELECT * FROM ingestion_audit_log").fetchall()
    con.close()
    return results


# --- Automated RBAC Matrix Verification Test ---
def run_security_rbac_test():
    test_identities = [
        {"username": "john_operator", "role": "OPERATOR"},
        {"username": "sarah_engineer", "role": "RELIABILITY_ENGINEER"},
        {"username": "raphael_sec", "role": "CYBER_SECURITY_AUDITOR"}
    ]
    
    print("=== RUNNING RBAC SECURITY MATRIX VERIFICATION ===")
    
    for identity in test_identities:
        # Dynamically switch the active session context
        CURRENT_USER_SESSION.update(identity)
        print(f"\n[TEST CONTEXT] User: {identity['username']} | Role: {identity['role']}")
        print("-" * 50)
        
        # Test 1: Operational Telemetry Access
        try:
            query_operational_telemetry()
            print("  [ACCESS GRANTED] Operational Telemetry")
        except PermissionError as e:
            print(f"  [ACCESS BLOCKED] Operational Telemetry -> Expected for {identity['role']}")
        
        # Test 2: Security Audit Logs Access
        try:
            query_security_audit_logs()
            print("  [ACCESS GRANTED] Security Audit Logs")
        except PermissionError as e:
            print(f"  [ACCESS BLOCKED] Security Audit Logs -> Expected for {identity['role']}")


if __name__ == "__main__":
    # Run the automated matrix verification test when executed directly
    run_security_rbac_test()