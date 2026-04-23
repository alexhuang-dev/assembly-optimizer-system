from __future__ import annotations

import pandas as pd
import streamlit as st

from core.config import DEFAULT_HISTORY_DB_PATH
from core.history import fetch_recent_runs

st.set_page_config(page_title="Assembly Optimizer", layout="wide")

st.title("Assembly Optimizer Dashboard")
st.caption("Interference-fit run history and assembly decision snapshots.")

rows = fetch_recent_runs(DEFAULT_HISTORY_DB_PATH, limit=30)

if not rows:
    st.info("No history yet. Run the API once and the dashboard will populate automatically.")
    st.stop()

frame = pd.DataFrame(rows)
st.metric("Recorded runs", len(frame))

left, right = st.columns(2)

with left:
    st.subheader("Recent runs")
    st.dataframe(frame, use_container_width=True)

with right:
    st.subheader("Trend view")
    trend = frame[["created_at", "safety_factor", "torque_margin", "press_force_kn"]].copy()
    trend = trend.sort_values("created_at")
    trend = trend.set_index("created_at")
    st.line_chart(trend, use_container_width=True)

latest = frame.iloc[0].to_dict()
st.subheader("Latest run summary")
st.json(latest)
