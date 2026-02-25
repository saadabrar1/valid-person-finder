"""
Streamlit UI for PersonFinderTool.

Run with:
    streamlit run streamlit_app.py
"""

import json
import streamlit as st

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Person Finder Tool",
    page_icon="🔍",
    layout="centered",
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("🔍 Person Finder Tool")
st.markdown(
    "Enter a **company name** and **designation** to find the person "
    "currently holding that role. Results are cross-validated across "
    "multiple search engines and scored for confidence."
)

st.divider()

# ---------------------------------------------------------------------------
# Input form
# ---------------------------------------------------------------------------
with st.form("person_finder_form"):
    col1, col2 = st.columns(2)
    with col1:
        company = st.text_input(
            "Company Name",
            placeholder="e.g. Microsoft",
            help="Full legal or commonly used name of the company.",
        )
    with col2:
        designation = st.text_input(
            "Designation",
            placeholder="e.g. CEO",
            help="Job title / designation to search for (aliases like CEO → Chief Executive Officer are handled automatically).",
        )

    submitted = st.form_submit_button("🔎 Search", use_container_width=True)

# ---------------------------------------------------------------------------
# Execution & display
# ---------------------------------------------------------------------------
if submitted:
    if not company.strip() or not designation.strip():
        st.error("Please fill in both **Company Name** and **Designation**.")
    else:
        with st.spinner("Searching and cross-validating across multiple sources…"):
            try:
                from src.main import find_person

                result = find_person(company.strip(), designation.strip())
            except Exception as exc:
                st.error(f"An unexpected error occurred: {exc}")
                result = None

        if result is not None:
            st.divider()

            # --- Error response ------------------------------------------
            if "error" in result and result.get("confidence_score", 0) == 0:
                st.warning(result["error"])

            # --- Success response ----------------------------------------
            else:
                confidence = result.get("confidence_score", 0.0)

                # Confidence progress bar
                st.subheader("Confidence Score")
                st.progress(
                    min(confidence, 1.0),
                    text=f"{confidence * 100:.1f}%",
                )

                # Person card
                st.subheader("Result")
                col_a, col_b = st.columns(2)
                with col_a:
                    st.metric("First Name", result.get("first_name", "—"))
                    st.metric("Title", result.get("current_title", "—"))
                with col_b:
                    st.metric("Last Name", result.get("last_name", "—"))
                    st.metric("Company", result.get("company", "—"))

                source_url = result.get("source_url", "")
                if source_url:
                    st.markdown(f"**Source:** [{source_url}]({source_url})")

                # Raw JSON expander
                with st.expander("📋 Raw JSON Output"):
                    st.code(json.dumps(result, indent=2), language="json")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.divider()
st.caption(
    "PersonFinderTool • Powered by LangChain + LangGraph + Groq • "
    "SerpAPI + DuckDuckGo cross-validation"
)
