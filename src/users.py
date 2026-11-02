import duckdb
import hashlib
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "nova_warehouse.duckdb"

def setup_iam_table(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS iam_users (
            username VARCHAR UNIQUE,
            role VARCHAR,
            salt VARCHAR,
            password_hash VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

def register_new_user():
    print("=========================================")
    print("   🛡️ NOVA IAM: Secure User Registration")
    print("=========================================")
    
    username = input("Enter new username: ").strip()
    if not username:
        print("❌ Error: Username cannot be empty.")
        return
        
    password = input("Enter password: ").strip()
    if not password:
        print("❌ Error: Password cannot be empty.")
        return
        
    print("\nSelect User Role Level:")
    print("  [1] OPERATOR")
    print("  [2] RELIABILITY_ENGINEER")
    print("  [3] CYBER_SECURITY_AUDITOR")
    
    role_choice = input("Enter choice (1-3): ").strip()
    role_mapping = {
        "1": "OPERATOR",
        "2": "RELIABILITY_ENGINEER",
        "3": "CYBER_SECURITY_AUDITOR"
    }
    
    role = role_mapping.get(role_choice)
    if not role:
        print("❌ Error: Invalid role selection. Registration aborted.")
        return
        
    con = duckdb.connect(str(DB_PATH))
    setup_iam_table(con)
    
    # Generate a cryptographically secure random salt
    salt = secrets.token_hex(16)
    
    # Salt and hash the password
    salted_password = salt.encode() + password.encode()
    password_hash = hashlib.sha256(salted_password).hexdigest()
    
    try:
        con.execute(
            "INSERT INTO iam_users (username, role, salt, password_hash) VALUES (?, ?, ?, ?)",
            [username, role, salt, password_hash]
        )
        print(f"\n✅ [SUCCESS] User '{username}' registered with role '{role}'.")
    except duckdb.ConstraintException:
        print(f"\n⚠️ [ALERT] User '{username}' already exists in the warehouse.")
    finally:
        con.close()

if __name__ == "__main__":
    register_new_user()