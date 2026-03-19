import streamlit as st
import pandas as pd
import re
import io
from openpyxl import load_workbook

# ─── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ID Splitter",
    page_icon="✂️",
    layout="centered",
)

# ─── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Main background */
    .stApp { background-color: #f7f8fa; }

    /* Hide default streamlit top header */
    header[data-testid="stHeader"] { display: none; }

    /* Card style */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 700px;
    }

    /* Title */
    h1 { font-size: 1.6rem !important; font-weight: 600 !important; }

    /* Metric cards */
    [data-testid="metric-container"] {
        background: white;
        border: 1px solid #e8eaf0;
        border-radius: 10px;
        padding: 12px 16px;
    }

    /* Pill tags */
    .pill-tag {
        display: inline-block;
        background: #eef2ff;
        color: #3730a3;
        font-size: 12px;
        font-family: monospace;
        padding: 3px 10px;
        border-radius: 20px;
        margin: 3px;
    }

    /* Success box */
    .success-box {
        background: #f0fdf4;
        border: 1px solid #86efac;
        border-radius: 10px;
        padding: 16px 20px;
        margin-top: 12px;
    }
</style>
""", unsafe_allow_html=True)


# ─── Session state defaults ──────────────────────────────────────────────────
if "uploaded_ids" not in st.session_state:
    st.session_state.uploaded_ids = []
if "result_ready" not in st.session_state:
    st.session_state.result_ready = False
if "output_bytes" not in st.session_state:
    st.session_state.output_bytes = None
if "summary" not in st.session_state:
    st.session_state.summary = {}


# ─── Header ──────────────────────────────────────────────────────────────────
st.markdown("## ✂️ ID Splitter")
st.markdown("Split any Excel or CSV file into separate sheets by ID group — no coding needed.")
st.divider()


# ─── Step 1: IDs ─────────────────────────────────────────────────────────────
st.markdown("### Step 1 — Enter your IDs")

col1, col2 = st.columns([3, 1])
with col1:
    manual_input = st.text_input(
        "Type an ID and press Add",
        placeholder="e.g. DOC88502 or 0061",
        label_visibility="collapsed"
    )
with col2:
    if st.button("Add ID", use_container_width=True):
        val = manual_input.strip()
        if val and val not in st.session_state.uploaded_ids:
            st.session_state.uploaded_ids.append(val)

# Upload ID sheet
id_file = st.file_uploader(
    "Or upload a sheet of IDs (.xlsx or .csv)",
    type=["xlsx", "csv"],
    key="id_upload"
)
if id_file:
    try:
        if id_file.name.endswith(".csv"):
            id_df = pd.read_csv(id_file, encoding="utf-8", on_bad_lines="skip")
        else:
            id_df = pd.read_excel(id_file)
        new_ids = id_df.iloc[:, 0].dropna().astype(str).tolist()
        combined = list(dict.fromkeys(st.session_state.uploaded_ids + new_ids))
        st.session_state.uploaded_ids = combined
        st.success(f"{len(new_ids)} IDs loaded from file.")
    except Exception as e:
        st.error(f"Could not read ID file: {e}")

# Show current ID pills
if st.session_state.uploaded_ids:
    pills_html = " ".join(
        f'<span class="pill-tag">{id_}</span>'
        for id_ in st.session_state.uploaded_ids
    )
    st.markdown(
        f'<div style="margin-top:8px;">{pills_html}</div>',
        unsafe_allow_html=True
    )
    if st.button("🗑️ Clear all IDs"):
        st.session_state.uploaded_ids = []
        st.rerun()
else:
    st.caption("No IDs added yet.")

st.divider()


# ─── Step 2: Data file ────────────────────────────────────────────────────────
st.markdown("### Step 2 — Upload your data file")

data_file = st.file_uploader(
    "Choose the Excel or CSV file to split",
    type=["xlsx", "csv"],
    key="data_upload"
)

st.divider()


# ─── Step 3: Options ─────────────────────────────────────────────────────────
st.markdown("### Step 3 — Options")

col_a, col_b = st.columns(2)
with col_a:
    show_preview = st.toggle("Show preview before download", value=True)
with col_b:
    include_errors = st.toggle("Include unmatched rows sheet", value=True)

st.divider()


# ─── Process ─────────────────────────────────────────────────────────────────
st.markdown("### Step 4 — Run")

run_clicked = st.button("▶ Run Splitter", type="primary", use_container_width=True)

if run_clicked:
    id_list = st.session_state.uploaded_ids

    # Validation
    if not id_list:
        st.error("Please add at least one ID (Step 1).")
        st.stop()
    if data_file is None:
        st.error("Please upload a data file (Step 2).")
        st.stop()

    with st.spinner("Reading file..."):
        try:
            if data_file.name.endswith(".csv"):
                df = pd.read_csv(data_file, encoding="utf-8", on_bad_lines="skip")
            else:
                df = pd.read_excel(data_file)
            df = df.astype(str)
        except Exception as e:
            st.error(f"Could not read data file: {e}")
            st.stop()

    # Detect column & position
    with st.spinner("Detecting ID column..."):
        detected_col = None
        position_index = None

        for col in df.columns:
            for val in df[col]:
                tokens = re.split(r"[ \-_]", val.upper())
                for i, token in enumerate(tokens):
                    if any(id_val.upper() in token for id_val in id_list):
                        detected_col = col
                        position_index = i
                        break
                if detected_col:
                    break
            if detected_col:
                break

        if detected_col is None:
            st.error("No matching ID found in the data file. Check your IDs and try again.")
            st.stop()

    # Column selector
    st.info(f"Auto-detected ID column: **{detected_col}**")
    best_col = st.selectbox(
        "Confirm or change the ID column:",
        options=list(df.columns),
        index=list(df.columns).index(detected_col)
    )

    # ── FIXED: extract_id now never returns a blank string ──
    def extract_id(value):
        tokens = re.split(r"[ \-_]", str(value).upper())
        if len(tokens) > position_index:
            result = tokens[position_index].strip()
            return result if result else "UNKNOWN"
        return "UNKNOWN"

    df["GROUP"] = df[best_col].apply(extract_id)

    # Preview
    if show_preview:
        st.markdown("#### Preview (first 10 rows)")
        st.dataframe(df.head(10), use_container_width=True)

        st.markdown("#### Group summary")
        summary_preview = df["GROUP"].value_counts().reset_index()
        summary_preview.columns = ["Group", "Row count"]
        st.dataframe(summary_preview, use_container_width=True)

    # Write output
    with st.spinner("Writing output sheets..."):
        error_df = df[df["GROUP"] == "UNKNOWN"]
        valid_df = df[df["GROUP"] != "UNKNOWN"]

        summary_df = (
            valid_df.groupby("GROUP")
            .size()
            .reset_index(name="ROW_COUNT")
            .sort_values(by="ROW_COUNT", ascending=False)
        )

        output = io.BytesIO()
        unique_ids = valid_df["GROUP"].unique()

        progress_bar = st.progress(0, text="Writing sheets...")
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            for i, uid in enumerate(unique_ids):
                group_df = valid_df[valid_df["GROUP"] == uid].drop(columns=["GROUP"])
                # ── FIXED: guarantee sheet name is never blank ──
                sheet_name = str(uid).strip()[:30]
                if not sheet_name:
                    sheet_name = f"GROUP_{i+1}"
                group_df.to_excel(writer, sheet_name=sheet_name, index=False)
                progress_bar.progress(
                    int((i + 1) / len(unique_ids) * 90),
                    text=f"Writing sheet {i+1} of {len(unique_ids)}: {sheet_name}"
                )

            summary_df.to_excel(writer, sheet_name="SUMMARY", index=False)

            if include_errors and not error_df.empty:
                error_df.drop(columns=["GROUP"]).to_excel(
                    writer, sheet_name="ERRORS", index=False
                )

        progress_bar.progress(100, text="Done!")

    st.session_state.output_bytes = output.getvalue()
    st.session_state.result_ready = True
    st.session_state.summary = {
        "sheets": len(unique_ids),
        "matched": len(valid_df),
        "unmatched": len(error_df),
    }


# ─── Result ──────────────────────────────────────────────────────────────────
if st.session_state.result_ready and st.session_state.output_bytes:
    s = st.session_state.summary

    st.markdown('<div class="success-box">', unsafe_allow_html=True)
    st.markdown("**✅ Done! Your file is ready.**")
    st.markdown('</div>', unsafe_allow_html=True)

    m1, m2, m3 = st.columns(3)
    m1.metric("Sheets created", s["sheets"])
    m2.metric("Rows matched", s["matched"])
    m3.metric("Unmatched rows", s["unmatched"])

    st.download_button(
        label="⬇️ Download Output Excel",
        data=st.session_state.output_bytes,
        file_name="id_splitter_output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        type="primary"
    )

    if st.button("🔄 Start over", use_container_width=True):
        for key in ["uploaded_ids", "result_ready", "output_bytes", "summary"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()