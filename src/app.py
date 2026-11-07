import streamlit as st
import duckdb
import pandas as pd
from pathlib import Path

# --- Configuration ---
st.set_page_config(page_title="Nova Enterprise Hub", layout="wide", page_icon="⚙️")
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "nova_warehouse.duckdb"

# --- UI Header ---
st.title("⚙️ Nova Industrial Telemetry & Security Hub")
st.markdown("*Asset: K-101 Industrial Gas Compressor | Pipeline: Multi-Source ETL & Cryptographic Ingestion*")
st.divider()

# --- Database Connection ---
@st.cache_resource
def get_connection():
    return duckdb.connect(str(DB_PATH), read_only=True)

con = get_connection()

# --- Department Tabs ---
tabs = st.tabs([
    "📈 Operational Telemetry", 
    "💰 Accounting & Finance", 
    "👥 Human Resources", 
    "🛡️ Cyber Security", 
    "💻 IT Support"
])

# Helper function to safely load tables
def load_table_data(query):
    try:
        return con.execute(query).df()
    except duckdb.CatalogException:
        return pd.DataFrame() # Return empty if table doesn't exist yet

# 1. Telemetry Tab
with tabs[0]:
    st.subheader("Real-Time Compressor Sensor Feed")
    df_telemetry = load_table_data("SELECT * FROM bronze_telemetry ORDER BY timestamp DESC LIMIT 100")
    if not df_telemetry.empty:
        st.dataframe(df_telemetry, use_container_width=True, hide_index=True)
    else:
        st.warning("Awaiting zero-trust ingestion for Operations Telemetry...")

# 2. Accounting Tab
with tabs[1]:
    st.subheader("Departmental Financial Ledger")
    df_accounting = load_table_data("SELECT * FROM bronze_accounting ORDER BY ingested_at DESC LIMIT 100")
    if not df_accounting.empty:
        st.dataframe(df_accounting, use_container_width=True, hide_index=True)
    else:
        st.warning("Awaiting zero-trust ingestion for Accounting...")

# 3. HR Tab
with tabs[2]:
    st.subheader("Facility Access & Employee Logs")
    df_hr = load_table_data("SELECT * FROM bronze_hr ORDER BY timestamp DESC LIMIT 100")
    if not df_hr.empty:
        st.dataframe(df_hr, use_container_width=True, hide_index=True)
    else:
        st.warning("Awaiting zero-trust ingestion for Human Resources...")

# 4. Security Tab
with tabs[3]:
    st.subheader("Network Threat & Access Audit")
    df_security = load_table_data("SELECT * FROM bronze_security ORDER BY event_time DESC LIMIT 100")
    if not df_security.empty:
        st.dataframe(df_security, use_container_width=True, hide_index=True)
    else:
        st.warning("Awaiting zero-trust ingestion for Cyber Security...")

# 5. IT Tab
with tabs[4]:
    st.subheader("Active System Incidents")
    df_it = load_table_data("SELECT * FROM bronze_it ORDER BY ingested_at DESC LIMIT 100")
    if not df_it.empty:
        st.dataframe(df_it, use_container_width=True, hide_index=True)
    else:
        st.warning("Awaiting zero-trust ingestion for IT Support...")