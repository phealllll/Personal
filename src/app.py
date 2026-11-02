import streamlit as st
import duckdb
from pathlib import Path
import hashlib
import secrets

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "nova_warehouse.duckdb"

st.set_page_config(
    page_title="Nova K-101 | OT Security & Telemetry Hub",
    page_icon="🛡️",
    layout="wide"
)

# --- Custom Industrial UI Styling ---
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #c9d1d9; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .metric-card {
        background-color: #161b22;
        border: 1px solid #30363d;
        padding: 20px;
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    section[data-testid="stSidebar"] {
        background-color: #111418;
        border-right: 1px solid #30363d;
    }
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
                new_role = st.selectbox("Assign Security Role", ["OPERATOR", "RELIABILITY_ENGINEER", "CYBER_SECURITY_AUDITOR"])
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
                            
    st.stop()

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

st.markdown("## ⚙️ Nova Industrial Telemetry & Security Hub")
st.markdown("##### *Asset: K-101 Industrial Gas Compressor | Pipeline: Multi-Source ETL & Cryptographic Ingestion*")
st.markdown("---")

# --- Data Fetching Functions ---
def fetch_telemetry_data(role):
    if role not in ["RELIABILITY_ENGINEER", "OPERATOR"]:
        raise PermissionError("Access Denied: Role not authorized for live operational telemetry.")
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = con.execute("SELECT timestamp, asset_id, temperature_c, pressure_psi, vibration_mm_s, power_kw FROM silver_telemetry ORDER BY timestamp DESC LIMIT 100").fetchdf()
    con.close()
    return df

def fetch_maintenance_logs(role):
    if role not in ["RELIABILITY_ENGINEER", "OPERATOR"]:
        raise PermissionError("Access Denied: Role not authorized for asset maintenance records.")
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = con.execute("SELECT log_id, technician, action_taken, parts_replaced, logged_at FROM maintenance_logs ORDER BY logged_at DESC LIMIT 50").fetchdf()
    con.close()
    return df

def fetch_audit_logs(role):
    if role not in ["RELIABILITY_ENGINEER", "CYBER_SECURITY_AUDITOR"]:
        raise PermissionError("Access Denied: Role not authorized for security compliance logs.")
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = con.execute("SELECT * FROM ingestion_audit_log ORDER BY verified_at DESC").fetchdf()
    con.close()
    return df

# --- Tab Layout ---
tab1, tab2, tab3 = st.tabs(["📈 Operational Telemetry", "🛠️ Maintenance Logs", "🛡️ Security & Ingestion Audit"])

with tab1:
    st.markdown("### Real-Time Compressor Sensor Feed")
    try:
        df_telemetry = fetch_telemetry_data(st.session_state['role'])
        col1, col2, col3 = st.columns(3)
        with col1: st.metric("📊 Active Rows Loaded", len(df_telemetry))
        with col2: st.metric("🌡️ Mean Temperature", f"{df_telemetry['temperature_c'].mean():.2f} °C" if not df_telemetry.empty else "0.00 °C")
        with col3: st.metric("⚙️ Avg Vibration", f"{df_telemetry['vibration_mm_s'].mean():.2f} mm/s" if not df_telemetry.empty else "0.00 mm/s")
        st.markdown("<br>", unsafe_allow_html=True)
        st.dataframe(df_telemetry, use_container_width=True, height=300)
        if not df_telemetry.empty:
            st.line_chart(df_telemetry.set_index('timestamp')[['temperature_c', 'pressure_psi']], use_container_width=True)
    except PermissionError as e:
        st.error(f"🚫 **RBAC SECURITY BLOCK:** {e}")
    except Exception as e:
        st.error(f"⚠️ **SYSTEM ERROR:** {e}")

with tab2:
    st.markdown("### K-101 Asset Maintenance History")
    try:
        df_maintenance = fetch_maintenance_logs(st.session_state['role'])
        st.markdown("<br>", unsafe_allow_html=True)
        st.dataframe(df_maintenance, use_container_width=True, height=400)
    except PermissionError as e:
        st.error(f"🚫 **RBAC SECURITY BLOCK:** {e}")
    except Exception as e:
        st.error(f"⚠️ **SYSTEM ERROR:** {e}")

with tab3:
    st.markdown("### Cryptographic Cross-Vault Audit Trail")
    try:
        df_audit = fetch_audit_logs(st.session_state['role'])
        st.markdown("<br>", unsafe_allow_html=True)
        st.dataframe(df_audit, use_container_width=True, height=450)
    except PermissionError as e:
        st.error(f"🚫 **RBAC SECURITY BLOCK:** {e}")
    except Exception as e:
        st.error(f"⚠️ **SYSTEM ERROR:** {e}")