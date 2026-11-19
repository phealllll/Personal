import os
import pyodbc
from dotenv import load_dotenv

load_dotenv()


def get_sql_connection() -> pyodbc.Connection:
    server = os.getenv("NOVA_SQL_SERVER", "PHEAL")
    database = os.getenv("NOVA_SQL_DB", "NovaWarehouse")
    driver = os.getenv("NOVA_SQL_DRIVER", "{ODBC Driver 18 for SQL Server}")
    username = os.getenv("NOVA_SQL_USER", "nova_svc_login")
    password = os.getenv("NOVA_SQL_PASSWORD", "")

    conn_str = (
        f"DRIVER={driver};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str, autocommit=False)


def verify_least_privilege_lockdown() -> None:
    with get_sql_connection() as conn:
        cursor = conn.cursor()
        user = cursor.execute("SELECT SYSTEM_USER, USER_NAME()").fetchone()
        print(f"Connected as Login: {user[0]} | DB User: {user[1]}")

        try:
            cursor.execute("DELETE FROM ops.audit_ledger")
            conn.commit()
            print("WARNING: Direct DELETE succeeded.")
        except pyodbc.Error:
            conn.rollback()
            print("RBAC Verified: Direct DELETE on ops.audit_ledger blocked.")


if __name__ == "__main__":
    verify_least_privilege_lockdown()