import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pyodbc
import streamlit as st
from dotenv import load_dotenv


load_dotenv()

st.set_page_config(
    page_title="NovaWarehouse | Zero-Trust Telemetry & Biometric Ops",
    layout="wide",
)


def get_readonly_connection() -> pyodbc.Connection:
    server = os.getenv("NOVA_SQL_SERVER", "PHEAL")
    database = os.getenv("NOVA_SQL_DB", "NovaWarehouse")
    driver = os.getenv("NOVA_SQL_DRIVER", "{ODBC Driver 18 for SQL Server}")
    username = os.getenv("NOVA_DASH_USER", "nova_dash_login")
    password = os.getenv("NOVA_DASH_PASSWORD", "")

    conn_str = (
        f"DRIVER={driver};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str, autocommit=True)


@st.cache_data(ttl=15)
def load_dashboard_data() -> dict[str, pd.DataFrame]:
    with get_readonly_connection() as conn:
        principal_df = pd.read_sql(
            "SELECT SYSTEM_USER AS sql_login, USER_NAME() AS db_user", conn
        )
        enrolled_employees_df = pd.read_sql(
            """
            SELECT
                e.employee_id,
                e.username,
                r.role_name,
                d.department_name,
                b.biometric_id,
                b.model_version,
                b.enrolled_at_utc,
                CASE WHEN b.biometric_id IS NOT NULL THEN 'ENROLLED' ELSE 'UNENROLLED' END AS face_status
            FROM dim.employee e
            JOIN dim.role r ON e.role_id = r.role_id
            JOIN dim.department d ON e.department_id = d.department_id
            LEFT JOIN dim.employee_biometric b ON e.employee_id = b.employee_id
            ORDER BY e.employee_id ASC
            """,
            conn,
        )
        assets_df = pd.read_sql(
            """
            SELECT a.asset_id, a.asset_name, a.asset_type, d.department_name,
                   a.assigned_operative_id, e.username AS operative_username, a.status
            FROM dim.asset a
            JOIN dim.department d ON a.department_id = d.department_id
            LEFT JOIN dim.employee e ON a.assigned_operative_id = e.employee_id
            """,
            conn,
        )
        telemetry_df = pd.read_sql(
            """
            SELECT t.reading_id, t.asset_id, a.asset_name, t.recorded_at_utc,
                   t.temperature_c, t.vibration_mm_s, t.source_batch,
                   t.handled_by_operative_id, e.username AS operative_username,
                   t.verification_id
            FROM fact.telemetry_reading t
            JOIN dim.asset a ON t.asset_id = a.asset_id
            LEFT JOIN dim.employee e ON t.handled_by_operative_id = e.employee_id
            ORDER BY t.recorded_at_utc ASC
            """,
            conn,
        )
        anomalies_df = pd.read_sql(
            """
            SELECT sa.anomaly_id, sa.asset_id, sa.severity, sa.description,
                   sa.detected_at_utc, sa.verified_by_operative_id,
                   e.username AS resolved_by, sa.resolved_flag
            FROM fact.security_anomaly sa
            LEFT JOIN dim.employee e ON sa.verified_by_operative_id = e.employee_id
            ORDER BY sa.detected_at_utc DESC
            """,
            conn,
        )
        verifications_df = pd.read_sql(
            """
            SELECT v.verification_id, v.employee_id, e.username, v.asset_id,
                   v.source_batch, v.anomaly_id, v.cv_confidence_score,
                   v.auth_status, v.frame_sha256, v.verified_at_utc
            FROM fact.operative_verification v
            JOIN dim.employee e ON v.employee_id = e.employee_id
            ORDER BY v.verified_at_utc DESC
            """,
            conn,
        )
        dq_df = pd.read_sql(
            """
            SELECT check_id, checked_at_utc, table_name, check_name, status, detail
            FROM ops.dq_validation_log
            ORDER BY checked_at_utc DESC
            """,
            conn,
        )
        audit_df = pd.read_sql(
            """
            SELECT event_id, event_timestamp_utc, employee_id, username,
                   role_name, action_performed, query_hash
            FROM ops.audit_ledger
            ORDER BY event_timestamp_utc DESC
            """,
            conn,
        )

    return {
        "principal": principal_df,
        "enrolled_employees": enrolled_employees_df,
        "assets": assets_df,
        "telemetry": telemetry_df,
        "anomalies": anomalies_df,
        "verifications": verifications_df,
        "dq": dq_df,
        "audit": audit_df,
    }


st.title("NovaWarehouse Operations & Biometric Attestation")

if st.sidebar.button("Refresh Warehouse Data"):
    st.cache_data.clear()

data = load_dashboard_data()
principal = data["principal"].iloc[0]
st.sidebar.markdown("### Zero-Trust Session")
st.sidebar.code(
    f"Login: {principal['sql_login']}\nUser:  {principal['db_user']}\nMode:  READ-ONLY"
)

telemetry_df = data["telemetry"]
anomalies_df = data["anomalies"]
verifications_df = data["verifications"]
enrolled_df = data["enrolled_employees"]

if telemetry_df.empty:
    st.warning("No telemetry readings found in NovaWarehouse. Run src/ingestor.py first.")
    st.stop()

batches = sorted(telemetry_df["source_batch"].unique(), reverse=True)
selected_batch = st.sidebar.selectbox("Select Telemetry Batch", batches)
batch_df = telemetry_df[telemetry_df["source_batch"] == selected_batch].copy()
batch_df["recorded_at_utc"] = pd.to_datetime(batch_df["recorded_at_utc"])

total_rows = len(batch_df)
verified_rows = int(batch_df["verification_id"].notna().sum())
enrolled_count = int((enrolled_df["face_status"] == "ENROLLED").sum())
open_anomalies = int((anomalies_df["resolved_flag"] == 0).sum()) if not anomalies_df.empty else 0
latest_conf = (
    float(verifications_df.iloc[0]["cv_confidence_score"])
    if not verifications_df.empty
    else 0.0
)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Batch Telemetry Rows", f"{total_rows:,}")
c2.metric("Biometrically Verified Rows", f"{verified_rows:,} / {total_rows:,}")
c3.metric("Enrolled Operatives", f"{enrolled_count} / {len(enrolled_df)}")
c4.metric("Open Security Anomalies", open_anomalies)
c5.metric("Latest CV Match Confidence", f"{latest_conf:.4f}")

tab_telemetry, tab_biometrics, tab_audit = st.tabs(
    ["Telemetry & Thresholds", "Biometric Gate & Anomalies", "DQ & Immutable Audit Ledger"]
)

with tab_telemetry:
    col_temp, col_vib = st.columns(2)

    with col_temp:
        fig_temp = px.line(
            batch_df,
            x="recorded_at_utc",
            y="temperature_c",
            title=f"Compressor Temperature (°C) — {selected_batch}",
            labels={"recorded_at_utc": "Timestamp (UTC)", "temperature_c": "Temperature (°C)"},
        )
        fig_temp.add_hline(
            y=90.0,
            line_dash="dash",
            line_color="red",
            annotation_text="Alert Threshold (90.0 °C)",
        )
        st.plotly_chart(fig_temp, width="stretch")

    with col_vib:
        fig_vib = px.line(
            batch_df,
            x="recorded_at_utc",
            y="vibration_mm_s",
            title=f"Mechanical Vibration (mm/s) — {selected_batch}",
            labels={"recorded_at_utc": "Timestamp (UTC)", "vibration_mm_s": "Vibration (mm/s)"},
        )
        fig_vib.add_hline(
            y=7.0,
            line_dash="dash",
            line_color="red",
            annotation_text="Alert Threshold (7.0 mm/s)",
        )
        st.plotly_chart(fig_vib, width="stretch")

    st.subheader("Threshold Breach Readings in Selected Batch")
    breach_df = batch_df[(batch_df["temperature_c"] > 90.0) | (batch_df["vibration_mm_s"] > 7.0)]
    st.dataframe(breach_df, width="stretch", hide_index=True)

    st.subheader("Monitored Infrastructure Assets")
    st.dataframe(data["assets"], width="stretch", hide_index=True)

with tab_biometrics:
    st.subheader("Registered Operative Biometric Directory")
    st.dataframe(enrolled_df, width="stretch", hide_index=True)

    st.subheader("Operative Facial Verification Gate History")
    if not verifications_df.empty:
        fig_conf = go.Figure(
            data=[
                go.Bar(
                    x=verifications_df["verification_id"],
                    y=verifications_df["cv_confidence_score"],
                    text=verifications_df["auth_status"],
                    textposition="auto",
                )
            ]
        )
        fig_conf.add_hline(
            y=0.363,
            line_dash="dash",
            line_color="green",
            annotation_text="SFace Cosine Threshold (0.363)",
        )
        fig_conf.update_layout(
            title="Biometric Cosine Similarity Scores by Scan Event",
            xaxis_title="Verification ID",
            yaxis_title="Cosine Confidence Score",
            yaxis=dict(range=[0, 1]),
        )
        st.plotly_chart(fig_conf, width="stretch")
        st.dataframe(verifications_df, width="stretch", hide_index=True)

    st.subheader("Security Anomalies & Operative Sign-Off")
    st.dataframe(anomalies_df, width="stretch", hide_index=True)

with tab_audit:
    st.subheader("Automated Data Quality & SHA-256 Manifest Checks")
    st.dataframe(data["dq"], width="stretch", hide_index=True)

    st.subheader("Immutable Append-Only Audit Ledger (ops.audit_ledger)")
    st.dataframe(data["audit"], width="stretch", hide_index=True)