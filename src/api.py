from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import duckdb
from pathlib import Path
import hashlib
import secrets

app = FastAPI(title="Nova API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "nova_warehouse.duckdb"

def setup_iam():
    con = duckdb.connect(str(DB_PATH), read_only=False)
    con.execute("""
        CREATE TABLE IF NOT EXISTS iam_users (
            username VARCHAR UNIQUE,
            role VARCHAR,
            salt VARCHAR,
            password_hash VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.close()

class AuthRequest(BaseModel):
    username: str
    password: str
    role: str = None

@app.post("/api/register")
def register(req: AuthRequest):
    setup_iam()
    con = duckdb.connect(str(DB_PATH), read_only=False)
    try:
        salt = secrets.token_hex(16)
        password_hash = hashlib.sha256((salt + req.password).encode()).hexdigest()
        con.execute(
            "INSERT INTO iam_users (username, role, salt, password_hash) VALUES (?, ?, ?, ?)",
            [req.username, req.role, salt, password_hash]
        )
        return {"status": "success", "message": f"User '{req.username}' registered successfully."}
    except Exception as e:
        if "ConstraintException" in str(type(e)) or "already exists" in str(e):
            raise HTTPException(status_code=400, detail="Username already taken")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        con.close()

@app.post("/api/login")
def login(req: AuthRequest):
    setup_iam()
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        user_record = con.execute("SELECT role, salt, password_hash FROM iam_users WHERE username = ?", [req.username]).fetchone()
        if user_record:
            db_role, db_salt, db_hash = user_record
            computed_hash = hashlib.sha256((db_salt + req.password).encode()).hexdigest()
            if computed_hash == db_hash:
                return {"status": "success", "role": db_role, "username": req.username}
        raise HTTPException(status_code=401, detail="Invalid credentials")
    finally:
        con.close()

@app.get("/api/data/{department}")
def get_department_data(department: str, role: str):
    # Strict RBAC Mapping
    rbac_rules = {
        "telemetry": ["OPERATOR", "SYSADMIN"],
        "accounting": ["FINANCE_CONTROLLER", "SYSADMIN"],
        "human-resources": ["HR_MANAGER", "SYSADMIN"],
        "security": ["CYBER_SECURITY_AUDITOR", "SYSADMIN"],
        "it": ["CYBER_SECURITY_AUDITOR", "OPERATOR", "SYSADMIN"]
    }
    
    allowed_roles = rbac_rules.get(department, [])
    if role not in allowed_roles:
        raise HTTPException(status_code=403, detail=f"RBAC SECURITY BLOCK: Role '{role}' is not authorized to access {department} records.")
        
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        # Map frontend routes to duckdb table names
        table_name = "bronze_hr" if department == "human-resources" else f"bronze_{department}"
        df = con.execute(f"SELECT * FROM {table_name} LIMIT 50").fetchdf()
        return df.to_dict(orient="records")
    except duckdb.CatalogException:
        raise HTTPException(status_code=404, detail=f"Awaiting zero-trust ingestion for {department}.")
    finally:
        con.close()