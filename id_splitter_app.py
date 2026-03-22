import streamlit as st
import pandas as pd
import re
import io

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Universal ID Splitter",
    page_icon="✂️",
    layout="wide",
)

st.markdown("""
<style>
    .stApp { background-color: #f4f6f8; }
    header[data-testid="stHeader"] { display: none; }
    .block-container { padding-top: 2rem; }
</style>
""", unsafe_allow_html=True)

# ─── Cached file reader ───────────────────────────────────────────────────────
@st.cache_data(show_spinner="Reading file...")
def read_file(file_bytes, file_name):
    if file_name.endswith(".csv"):
        return pd.read_csv(
            io.BytesIO(file_bytes),
            encoding="utf-8",
            on_bad_lines="skip",
            dtype=str,
            low_memory=False
        )
    else:
        return pd.read_excel(
            io.BytesIO(file_bytes),
            dtype=str
        )

# ─── Session state ────────────────────────────────────────────────────────────
for key, default in {
    "uploaded_ids": [],
    "output_bytes": None,
    "result_summary": None,
    "detected_col": None,
    "position_index": None,
    "df": None,
    "all_columns": [],
    "show_preview": True,
    "id_list": [],
    "processing_done": False,
    "id_file_name": None,
    "data_file_name": None,
    "cached_data_df": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ─── Title ────────────────────────────────────────────────────────────────────
st.title("📊 Universal ID Splitter")
st.divider()

# ─── Sidebar ─────────────────────────────────────────────────────────────────
st.sidebar.header("Inputs")

manual_id    = st.sidebar.text_input("Enter ID", placeholder="e.g. DOC88502 or 0061")
id_file      = st.sidebar.file_uploader("Upload ID Sheet", type=["xlsx", "csv"])
data_file    = st.sidebar.file_uploader("Upload Data File", type=["xlsx", "csv"])
show_preview = st.sidebar.checkbox("Show Preview", value=True)

# Read ID file — cached
if id_file:
    if id_file.name != st.session_state.id_file_name:
        try:
            id_df = read_file(id_file.read(), id_file.name)
            st.session_state.uploaded_ids = id_df.iloc[:, 0].dropna().astype(str).tolist()
            st.session_state.id_file_name = id_file.name
        except Exception as e:
            st.sidebar.error(f"Error reading ID file: {e}")
    st.sidebar.success(f"{len(st.session_state.uploaded_ids)} IDs loaded ✅")

# Read data file — cached
if data_file:
    if data_file.name != st.session_state.data_file_name:
        try:
            cached_df = read_file(data_file.read(), data_file.name)
            st.session_state.cached_data_df = cached_df
            st.session_state.data_file_name = data_file.name
        except Exception as e:
            st.sidebar.error(f"Error reading data file: {e}")
    st.sidebar.success(f"Data file ready ✅: {data_file.name}")

# ─── STEP 1: Process File ─────────────────────────────────────────────────────
if st.sidebar.button("🚀 Process File"):

    for key in ["output_bytes", "result_summary", "detected_col", "position_index",
                "df", "all_columns", "id_list", "processing_done"]:
        st.session_state[key] = False if key == "processing_done" else None if key not in ["all_columns", "id_list"] else []

    id_list = []
    if manual_id.strip():
        id_list.append(manual_id.strip())
    if st.session_state.uploaded_ids:
        id_list.extend(st.session_state.uploaded_ids)

    if not id_list:
        st.error("Provide at least one ID")
        st.stop()

    if st.session_state.cached_data_df is None:
        st.error("Please upload a data file")
        st.stop()

    df = st.session_state.cached_data_df.copy()

    # ── FIXED DETECTION: finds exact token position where ID sits ─────────
    detected_col   = None
    position_index = None
    match_type     = None  # "exact_cell" or "token"

    for col in df.columns:
        for val in df[col]:
            val_str   = str(val).strip()
            val_upper = val_str.upper()

            # 1. Exact full cell match
            if any(id_val.strip().upper() == val_upper for id_val in id_list):
                detected_col   = col
                position_index = None
                match_type     = "exact_cell"
                break

            # 2. Token match — split by space, dash, underscore
            tokens = re.split(r"[ \-_]", val_upper)
            for i, token in enumerate(tokens):
                clean_token = token.strip()
                if any(id_val.strip().upper() == clean_token for id_val in id_list):
                    detected_col   = col
                    position_index = i
                    match_type     = "token"
                    break

            # 3. Substring match fallback
            if not detected_col:
                if any(id_val.strip().upper() in val_upper for id_val in id_list):
                    detected_col   = col
                    position_index = None
                    match_type     = "substring"
                    break

            if detected_col:
                break
        if detected_col:
            break

    if not detected_col:
        st.error("No matching ID found")
        st.stop()

    # Persist to session state
    st.session_state.detected_col   = detected_col
    st.session_state.position_index = position_index
    st.session_state.match_type     = match_type
    st.session_state.df             = df
    st.session_state.all_columns    = list(df.columns)
    st.session_state.show_preview   = show_preview
    st.session_state.id_list        = id_list


# ─── STEP 2: Dropdown + validation + live preview ─────────────────────────────
if st.session_state.detected_col is not None and st.session_state.df is not None and not st.session_state.processing_done:

    st.success(f"Detected column: **{st.session_state.detected_col}**")

    selected_col = st.selectbox(
        "Confirm or change column:",
        options=st.session_state.all_columns,
        index=st.session_state.all_columns.index(st.session_state.detected_col),
        key="col_selectbox"
    )

    df             = st.session_state.df
    position_index = st.session_state.position_index
    match_type     = st.session_state.get("match_type", "substring")
    id_list        = st.session_state.id_list

    # Validate entered ID exists in selected column
    col_values_upper = df[selected_col].str.strip().str.upper()
    id_found_in_col  = any(
        col_values_upper.str.contains(id_val.strip().upper(), regex=False).any()
        for id_val in id_list
    )

    if not id_found_in_col:
        st.error(
            f"❌ None of the entered IDs were found in column **'{selected_col}'**. "
            f"Please choose a different column that contains your ID."
        )
        st.stop()

    # ── FIXED GROUP EXTRACTION ────────────────────────────────────────────
    # If token match: extract value at the detected token position for every row
    # If exact/substring: use the full cell value
    def extract_group(value):
        val_str = str(value).strip()
        if not val_str or val_str.upper() == "NAN":
            return "UNKNOWN"

        if match_type == "token" and position_index is not None:
            tokens = re.split(r"[ \-_]", val_str)
            if len(tokens) > position_index:
                result = tokens[position_index].strip()
                return result if result else "UNKNOWN"
            return "UNKNOWN"
        else:
            # Exact cell or substring — use full cell value as group
            return val_str if val_str else "UNKNOWN"

    df["GROUP"] = df[selected_col].apply(extract_group)
    df["GROUP"] = df["GROUP"].replace("", "UNKNOWN")

    error_df = df[df["GROUP"] == "UNKNOWN"]
    valid_df = df[df["GROUP"] != "UNKNOWN"]

    summary_df = (
        valid_df.groupby("GROUP")
        .size()
        .reset_index(name="ROW_COUNT")
        .sort_values(by="ROW_COUNT", ascending=False)
    )

    # Metrics
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Rows", len(df))
    c2.metric("Matched Rows", len(valid_df))
    c3.metric("Unmatched Rows", len(error_df))

    # Preview
    st.subheader("Preview (First 10 Rows)")
    st.dataframe(df.head(10), use_container_width=True)

    st.subheader("Group Summary")
    st.dataframe(summary_df, use_container_width=True)

    st.divider()

    # Export button
    if st.button("📥 Confirm & Export", type="primary", use_container_width=True):

        output     = io.BytesIO()
        unique_ids = valid_df["GROUP"].unique()

        progress_bar = st.progress(0, text="Writing sheets...")
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            for i, uid in enumerate(unique_ids):
                group_df   = valid_df[valid_df["GROUP"] == uid].drop(columns=["GROUP"])
                sheet_name = re.sub(r"[\\/*?:\[\]]", "", str(uid)).strip()[:30]
                if not sheet_name:
                    sheet_name = f"GROUP_{i+1}"
                group_df.to_excel(writer, sheet_name=sheet_name, index=False)
                progress_bar.progress(
                    int((i + 1) / len(unique_ids) * 90),
                    text=f"Writing sheet {i+1} of {len(unique_ids)}: {sheet_name}"
                )
            summary_df.to_excel(writer, sheet_name="SUMMARY", index=False)
            if not error_df.empty:
                error_df.drop(columns=["GROUP"]).to_excel(writer, sheet_name="ERRORS", index=False)

        progress_bar.progress(100, text="Done!")

        st.session_state.output_bytes    = output.getvalue()
        st.session_state.result_summary  = {"sheets": len(unique_ids), "unmatched": len(error_df)}
        st.session_state.processing_done = True
        st.session_state.detected_col    = None
        st.session_state.df              = None
        st.rerun()


# ─── STEP 3: Download ─────────────────────────────────────────────────────────
if st.session_state.processing_done and st.session_state.output_bytes:
    s = st.session_state.result_summary
    st.success(f"✅ Done! {s['sheets']} sheets created, {s['unmatched']} unmatched rows")

    st.download_button(
        label="📥 Download Processed File",
        data=st.session_state.output_bytes,
        file_name="processed_output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        type="primary"
    )

    if st.button("🔄 Start Over"):
        for key in ["uploaded_ids", "output_bytes", "result_summary", "detected_col",
                    "position_index", "df", "all_columns", "id_list",
                    "id_file_name", "data_file_name", "cached_data_df"]:
            st.session_state[key] = [] if key in ["uploaded_ids", "all_columns", "id_list"] else None
        st.session_state.processing_done = False
        st.rerun()
