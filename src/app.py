import streamlit as st
import duckdb
import pandas as pd
from pathlib import Path
import hashlib
import secrets

# --- Configuration & Styling ---
st.set_page_config(page_title="Nova Enterprise Hub", layout="wide", page_icon="⚙️")
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "nova_warehouse.duckdb"

st.markdown("""
    <style>
    /* Custom Card Containers */
    .stMetric, div[data-testid="stVerticalBlock"] > div:has(div.stDataFrame) {
        background-color: rgba(30, 41, 59, 0.5);
        border: 1px solid rgba(0, 243, 255, 0.2);
        border-radius: 12px;
        padding: 15px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }
    /* Style headers */
    h1, h2, h3 {
        letter-spacing: 1px;
    }
    </style>
""", unsafe_allow_html=True)

# --- Database IAM Helper Functions ---
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

def authenticate_user(username, password):
    con = duckdb.connect(str(DB_PATH), read_only=False)
    try:
        setup_iam_table(con)
        user_record = con.execute("SELECT role, salt, password_hash FROM iam_users WHERE username = ?", [username]).fetchone()
        
        if user_record:
            db_role, db_salt, db_hash = user_record
            computed_hash = hashlib.sha256((db_salt + password).encode()).hexdigest()
            if computed_hash == db_hash:
                return db_role
        return None
    finally:
        con.close()

def register_user_in_db(username, password, role):
    con = duckdb.connect(str(DB_PATH), read_only=False)
    try:
        setup_iam_table(con)
        salt = secrets.token_hex(16)
        password_hash = hashlib.sha256((salt + password).encode()).hexdigest()
        
        con.execute(
            "INSERT INTO iam_users (username, role, salt, password_hash) VALUES (?, ?, ?, ?)",
            [username, role, salt, password_hash]
        )
        return True, f"User '{username}' registered successfully!"
    except Exception as e:
        if "ConstraintException" in str(type(e)) or "already exists" in str(e):
            return False, f"Username '{username}' is already taken."
        return False, f"Registration error: {e}"
    finally:
        con.close()

# --- Session State ---
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
    st.session_state["username"] = None
    st.session_state["role"] = None

# --- IAM GATEWAY UI ---
if not st.session_state["authenticated"]:
    st.markdown("<h2 style='text-align: center;'>🛡️ Nova IAM Security Gateway</h2>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        auth_mode = st.radio("Mode", ["🔑 Login", "📝 Register"], horizontal=True, label_visibility="collapsed")
        
        if auth_mode == "🔑 Login":
            with st.form("login_form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                if st.form_submit_button("Authenticate", use_container_width=True):
                    role = authenticate_user(username, password)
                    if role:
                        st.session_state["authenticated"] = True
                        st.session_state["username"] = username
                        st.session_state["role"] = role
                        st.rerun()
                    else:
                        st.error("Invalid credentials.")
        else:
            with st.form("register_form"):
                new_user = st.text_input("Username")
                new_pass = st.text_input("Password", type="password")
                new_role = st.selectbox("Role", ["SYSADMIN", "OPERATOR", "FINANCE_CONTROLLER", "HR_MANAGER", "CYBER_SECURITY_AUDITOR"])
                if st.form_submit_button("Register", use_container_width=True):
                    success, msg = register_user_in_db(new_user.strip(), new_pass.strip(), new_role)
                    if success: st.success(msg)
                    else: st.error(msg)
    st.stop()

# --- SECURE BACKEND DASHBOARD ---
st.sidebar.markdown(f"**User:** `{st.session_state['username']}`")
st.sidebar.markdown(f"**Role:** `{st.session_state['role']}`")
if st.sidebar.button("Log Out", use_container_width=True):
    st.session_state["authenticated"] = False
    st.rerun()

st.title("⚙️ Nova Industrial Telemetry & Security Hub")
st.divider()

con = duckdb.connect(str(DB_PATH), read_only=True)

def load_secure_table(query, required_roles):
    if st.session_state["role"] not in required_roles and st.session_state["role"] != "SYSADMIN":
        st.error(f"🚫 **RBAC SECURITY BLOCK:** Role `{st.session_state['role']}` is unauthorized.")
        return None
    try:
        return con.execute(query).df()
    except Exception:
        st.warning("Awaiting zero-trust ingestion for this vault...")
        return None

tabs = st.tabs(["📈 Telemetry", "💰 Accounting", "👥 HR", "🛡️ Security", "💻 IT Support"])

with tabs[0]:
    df = load_secure_table("SELECT * FROM bronze_telemetry LIMIT 50", ["OPERATOR", "SYSADMIN"])
    if df is not None and not df.empty:
        st.dataframe(df, use_container_width=True)
        st.line_chart(df, x="timestamp", y="temperature_c")

with tabs[1]:
    df = load_secure_table("SELECT * FROM bronze_accounting LIMIT 50", ["FINANCE_CONTROLLER", "SYSADMIN"])
    if df is not None and not df.empty:
        st.dataframe(df, use_container_width=True)
        st.bar_chart(df, x="cost_center", y="amount")

with tabs[2]:
    df = load_secure_table("SELECT * FROM bronze_hr LIMIT 50", ["HR_MANAGER", "SYSADMIN"])
    if df is not None and not df.empty:
        st.dataframe(df, use_container_width=True)

with tabs[3]:
    df = load_secure_table("SELECT * FROM bronze_security LIMIT 50", ["CYBER_SECURITY_AUDITOR", "SYSADMIN"])
    if df is not None and not df.empty:
        st.dataframe(df, use_container_width=True)

with tabs[4]:
    df = load_secure_table("SELECT * FROM bronze_it LIMIT 50", ["CYBER_SECURITY_AUDITOR", "OPERATOR", "SYSADMIN"])
    if df is not None and not df.empty:
        st.dataframe(df, use_container_width=True)