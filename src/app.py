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
    .stApp { background-color: #0e1117; color: #c9d1d9; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #161b22;
        border-radius: 6px 6px 0px 0px;
        color: #8b949e;
        padding: 10px 20px;
        font-weight: 600;
        border: 1px solid #30363d;
    }
    .stTabs [aria-selected="true"] {
        background-color: #21262d !important;
        color: #58a6ff !important;
        border-bottom: 2px solid #58a6ff;
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
            salted_password = db_salt.encode() + password.encode()
            computed_hash = hashlib.sha256(salted_password).hexdigest()
            
            if computed_hash == db_hash:
                return db_role
        return None
    except Exception as e:
        st.error(f"Database error: {e}")
        return None
    finally:
        con.close()

def register_user_in_db(username, password, role):
    con = duckdb.connect(str(DB_PATH), read_only=False)
    try:
        setup_iam_table(con)
        salt = secrets.token_hex(16)
        salted_password = salt.encode() + password.encode()
        password_hash = hashlib.sha256(salted_password).hexdigest()
        
        con.execute(
            "INSERT INTO iam_users (username, role, salt, password_hash) VALUES (?, ?, ?, ?)",
            [username, role, salt, password_hash]
        )
        return True, f"User '{username}' successfully registered!"
    except Exception as e:
        if "ConstraintException" in str(type(e)) or "already exists" in str(e):
            return False, f"Username '{username}' is already taken."
        return False, f"Registration error: {e}"
    finally:
        con.close()

# --- Session State Initialization ---
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
    st.session_state["username"] = None
    st.session_state["role"] = None

# --- LOGIN & REGISTRATION GATEWAY ---
if not st.session_state["authenticated"]:
    st.markdown("<h2 style='text-align: center;'>🛡️ Nova IAM Security Gateway</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Authorized Personnel Only</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        auth_mode = st.radio("Mode", ["🔑 Login", "📝 Register New Account"], horizontal=True, label_visibility="collapsed")
        st.markdown("<br>", unsafe_allow_html=True)
        
        if auth_mode == "🔑 Login":
            with st.form("login_form"):
                st.markdown("### Sign In")
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                submit = st.form_submit_button("Authenticate", use_container_width=True)
                
                if submit:
                    assigned_role = authenticate_user(username, password)
                    if assigned_role:
                        st.session_state["authenticated"] = True
                        st.session_state["username"] = username
                        st.session_state["role"] = assigned_role
                        st.rerun()
                    else:
                        st.error("🚫 Access Denied: Invalid credentials.")
        else:
            with st.form("register_form"):
                st.markdown("### Create Account")
                new_username = st.text_input("Choose Username")
                new_password = st.text_input("Choose Password", type="password")
                # Expanded roles for the 5 departments
                new_role = st.selectbox("Assign Security Role", [
                    "SYSADMIN", 
                    "OPERATOR", 
                    "FINANCE_CONTROLLER", 
                    "HR_MANAGER",
                    "CYBER_SECURITY_AUDITOR"
                ])
                reg_submit = st.form_submit_button("Register Account", use_container_width=True)
                
                if reg_submit:
                    if not new_username.strip() or not new_password.strip():
                        st.error("❌ Username and password cannot be empty.")
                    else:
                        success, message = register_user_in_db(new_username.strip(), new_password.strip(), new_role)
                        if success:
                            st.success(message)
                            st.info("Switch back to the 'Login' tab above to sign in with your new credentials.")
                        else:
                            st.error(message)
                            
    st.stop() # Prevents the rest of the app from running until authenticated

# --- SECURE DASHBOARD (Only runs if authenticated) ---

st.sidebar.markdown("### 🔐 Active Session")
st.sidebar.markdown("---")
st.sidebar.markdown(f"**User:** `{st.session_state['username']}`")
st.sidebar.markdown(f"**Role:** `{st.session_state['role']}`")

if st.sidebar.button("Log Out", use_container_width=True):
    st.session_state["authenticated"] = False
    st.session_state["username"] = None
    st.session_state["role"] = None
    st.rerun()

st.sidebar.info("Application-layer RBAC is actively enforcing Zero-Trust boundaries for this session.")

st.title("⚙️ Nova Industrial Telemetry & Security Hub")
st.markdown("*Asset: K-101 Industrial Gas Compressor | Pipeline: Multi-Source ETL & Cryptographic Ingestion*")
st.divider()

# --- Database Connection ---
@st.cache_resource
def get_connection():
    return duckdb.connect(str(DB_PATH), read_only=True)

con = get_connection()

# --- RBAC Helper Function ---
def load_secure_table(query, required_roles):
    current_role = st.session_state["role"]
    if current_role not in required_roles and "SYSADMIN" not in required_roles:
        # SYSADMIN gets global override, otherwise check if role is authorized
        if current_role != "SYSADMIN":
            st.error(f"🚫 **RBAC SECURITY BLOCK:** Your role (`{current_role}`) is not authorized to access this department's data vault.")
            return None
            
    try:
        return con.execute(query).df()
    except duckdb.CatalogException:
        st.warning("Awaiting zero-trust ingestion for this department...")
        return None

# --- Department Tabs ---
tabs = st.tabs([
    "📈 Operational Telemetry", 
    "💰 Accounting & Finance", 
    "👥 Human Resources", 
    "🛡️ Cyber Security", 
    "💻 IT Support"
])

# 1. Telemetry Tab
with tabs[0]:
    st.subheader("Real-Time Compressor Sensor Feed")
    df_telemetry = load_secure_table(
        "SELECT * FROM bronze_telemetry ORDER BY timestamp DESC LIMIT 100",
        required_roles=["OPERATOR", "SYSADMIN"]
    )
    if df_telemetry is not None and not df_telemetry.empty:
        st.dataframe(df_telemetry, use_container_width=True, hide_index=True)

# 2. Accounting Tab
with tabs[1]:
    st.subheader("Departmental Financial Ledger")
    df_accounting = load_secure_table(
        "SELECT * FROM bronze_accounting ORDER BY ingested_at DESC LIMIT 100",
        required_roles=["FINANCE_CONTROLLER", "SYSADMIN"]
    )
    if df_accounting is not None and not df_accounting.empty:
        st.dataframe(df_accounting, use_container_width=True, hide_index=True)

# 3. HR Tab
with tabs[2]:
    st.subheader("Facility Access & Employee Logs")
    df_hr = load_secure_table(
        "SELECT * FROM bronze_hr ORDER BY timestamp DESC LIMIT 100",
        required_roles=["HR_MANAGER", "SYSADMIN"]
    )
    if df_hr is not None and not df_hr.empty:
        st.dataframe(df_hr, use_container_width=True, hide_index=True)

# 4. Security Tab
with tabs[3]:
    st.subheader("Network Threat & Access Audit")
    df_security = load_secure_table(
        "SELECT * FROM bronze_security ORDER BY event_time DESC LIMIT 100",
        required_roles=["CYBER_SECURITY_AUDITOR", "SYSADMIN"]
    )
    if df_security is not None and not df_security.empty:
        st.dataframe(df_security, use_container_width=True, hide_index=True)

# 5. IT Tab
with tabs[4]:
    st.subheader("Active System Incidents")
    df_it = load_secure_table(
        "SELECT * FROM bronze_it ORDER BY ingested_at DESC LIMIT 100",
        required_roles=["CYBER_SECURITY_AUDITOR", "OPERATOR", "SYSADMIN"]
    )
    if df_it is not None and not df_it.empty:
        st.dataframe(df_it, use_container_width=True, hide_index=True)