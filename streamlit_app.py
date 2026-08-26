"""
CFPB Consumer Complaint Topic Explorer
Group 8 — Customer Complaint Topic Modelling (NMF, K=10)

Three tabs:
  1. Overview        — topic distribution across the corpus
  2. Explore Topics   — browse representative complaints per topic
  3. Classify Text     — paste a new complaint, see live topic assignment

Expected files in the same folder as this script:
  final_topic_interpretation_k10.csv   (topic, topic_label, document_count, percentage, top_terms, ...)
  representative_complaints_k10.csv    (topic, rank, text, ...)
  topic_terms_k10.json                 ({"1": [...], "2": [...], ...})
  tfidf_vectorizer.joblib              (from save_model_artifacts.py)
  nmf_model.joblib                     (from save_model_artifacts.py)
  topic_labels.json                    (from save_model_artifacts.py)
"""

import json
import os

import joblib
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="CFPB Complaint Topic Explorer",
    page_icon="\U0001F4CA",
    layout="wide",
)

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

st.markdown(
    """
    <style>
    .hero-banner {
        background: linear-gradient(135deg, #1F1F3A 0%, #27297C 60%, #3A3A6B 100%);
        padding: 28px 32px;
        border-radius: 12px;
        border-left: 6px solid #CFA54F;
        margin-bottom: 24px;
    }
    .hero-banner h1 {
        color: #FAFAFA;
        margin-bottom: 4px;
    }
    .hero-banner p {
        color: #D8D4C8;
        margin: 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

FALLBACK_LABELS = {
    "1": "Credit Report and Inquiry Problems",
    "2": "FCRA Privacy and Legal Rights",
    "3": "Bank, Card and Account Problems",
    "4": "Cash App Disputes",
    "5": "Identity Theft and Fraudulent Credit Reporting",
    "6": "Debt Collection and Debt Validation",
    "7": "FCRA Credit Reporting Disputes",
    "8": "Loan, Mortgage and Payment Problems",
    "9": "FCRA Furnisher and Statutory Obligations",
    "10": "Zelle Disputes",
}


@st.cache_data
def load_topic_labels():
    path = os.path.join(DATA_DIR, "topic_labels.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return FALLBACK_LABELS


@st.cache_data
def load_prevalence():
    path = os.path.join(DATA_DIR, "final_topic_interpretation_k10.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    return df


@st.cache_data
def load_representatives():
    path = os.path.join(DATA_DIR, "representative_complaints_k10.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path)
    return df


@st.cache_data
def load_topic_terms():
    path = os.path.join(DATA_DIR, "topic_terms_k10.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@st.cache_resource
def load_model_artifacts():
    vec_path = os.path.join(DATA_DIR, "tfidf_vectorizer.joblib")
    model_path = os.path.join(DATA_DIR, "nmf_model.joblib")
    if not (os.path.exists(vec_path) and os.path.exists(model_path)):
        return None, None
    vectorizer = joblib.load(vec_path)
    model = joblib.load(model_path)
    return vectorizer, model


topic_labels = load_topic_labels()
prevalence_df = load_prevalence()
representatives_df = load_representatives()
topic_terms = load_topic_terms()
vectorizer, nmf_model = load_model_artifacts()


# ------------------------------------------------------------------
# SIDEBAR
# ------------------------------------------------------------------

with st.sidebar:
    st.markdown("## About This Project")
    st.markdown(
        "**Customer Complaint Topic Modelling**\n\n"
        "MSc Business Analytics — Text Analytics Group Project, Group 8."
    )

    st.markdown("---")
    st.markdown("### Model Summary")
    st.markdown(
        "- **Dataset:** CFPB consumer complaints (2022–2024)\n"
        "- **Documents modelled:** 29,516 unique narratives\n"
        "- **Representation:** TF-IDF (unigrams + bigrams, 50,000 features)\n"
        "- **Best model:** NMF, K = 10\n"
        "- **Also evaluated:** LDA (K = 10)\n"
        "- **Stability:** 8/10 topics highly stable across 5 random seeds"
    )

    st.markdown("---")
    st.markdown("### Topic Legend")
    if prevalence_df is not None:
        legend_df = prevalence_df[["topic", "topic_label", "percentage"]].sort_values(
            "percentage", ascending=False
        )
        for _, r in legend_df.iterrows():
            st.markdown(f"**{int(r['topic'])}.** {r['topic_label']} — {r['percentage']:.1f}%")
    else:
        for k, v in sorted(topic_labels.items(), key=lambda x: int(x[0])):
            st.markdown(f"**{k}.** {v}")

    st.markdown("---")
    st.caption(
        "Built with NMF (scikit-learn) on TF-IDF-vectorised CFPB complaint "
        "narratives. See the accompanying written report for full methodology, "
        "evaluation, and limitations."
    )


# ------------------------------------------------------------------
# HEADER BANNER
# ------------------------------------------------------------------

st.markdown(
    """
    <div class="hero-banner">
        <h1>CFPB Consumer Complaint Topic Explorer</h1>
        <p>Group 8 — Customer Complaint Topic Modelling · NMF (K=10) fitted on
        29,516 CFPB consumer complaint narratives (2022–2024), represented via TF-IDF.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_overview, tab_explore, tab_classify = st.tabs(
    ["\U0001F4CA Overview", "\U0001F50D Explore Topics", "\u270D\uFE0F Classify New Complaint"]
)


with tab_overview:
    st.subheader("Topic Distribution Across the Corpus")

    if prevalence_df is not None:
        plot_df = prevalence_df.sort_values("percentage", ascending=True)
        fig = px.bar(
            plot_df,
            x="percentage",
            y="topic_label",
            orientation="h",
            text="percentage",
            labels={"percentage": "Percentage of complaints", "topic_label": "Topic"},
            title="Topic Prevalence — NMF K=10",
        )
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside", marker_color="#CFA54F")
        fig.update_layout(height=500, margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig, use_container_width=True)

        col1, col2, col3 = st.columns(3)
        top4 = prevalence_df.sort_values("percentage", ascending=False).head(4)
        col1.metric("Documents modelled", f"{int(prevalence_df['document_count'].sum()):,}")
        col2.metric("Topics", f"{len(prevalence_df)}")
        col3.metric("Top 4 topics share", f"{top4['percentage'].sum():.1f}%")

        st.subheader("Full Topic Table")
        display_cols = [c for c in ["topic", "topic_label", "document_count", "percentage", "top_terms"] if c in prevalence_df.columns]
        st.dataframe(
            prevalence_df[display_cols].sort_values("percentage", ascending=False),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.warning(
            "final_topic_interpretation_k10.csv not found in the app folder. "
            "Add it alongside streamlit_app.py to show the topic distribution."
        )


with tab_explore:
    st.subheader("Browse Representative Complaints by Topic")

    topic_options = {f"Topic {k}: {v}": k for k, v in topic_labels.items()}
    selected_label = st.selectbox("Choose a topic", list(topic_options.keys()))
    selected_topic = int(topic_options[selected_label])

    if topic_terms is not None and str(selected_topic) in topic_terms:
        st.markdown("**Top terms:** " + ", ".join(topic_terms[str(selected_topic)][:12]))

    if prevalence_df is not None:
        row = prevalence_df[prevalence_df["topic"] == selected_topic]
        if not row.empty:
            st.markdown(
                f"**{int(row['document_count'].iloc[0]):,} complaints** "
                f"({row['percentage'].iloc[0]:.2f}% of the corpus)"
            )

    st.markdown("---")

    if representatives_df is not None:
        subset = representatives_df[representatives_df["topic"] == selected_topic]
        if "rank" in subset.columns:
            subset = subset.sort_values("rank")
        if subset.empty:
            st.info("No representative complaints found for this topic.")
        else:
            for _, r in subset.iterrows():
                rank_label = f"Example {int(r['rank'])}" if "rank" in subset.columns else "Example"
                with st.expander(rank_label):
                    st.write(r.get("text", "(no text available)"))
    else:
        st.warning(
            "representative_complaints_k10.csv not found in the app folder. "
            "Add it alongside streamlit_app.py to browse example complaints."
        )


with tab_classify:
    st.subheader("Classify a New Complaint")
    st.caption(
        "Paste complaint text below to see which of the 10 discovered topics "
        "it is most associated with, using the trained NMF model."
    )

    if vectorizer is None or nmf_model is None:
        st.error(
            "Model files not found. Run save_model_artifacts.py in PyCharm first, "
            "then copy tfidf_vectorizer.joblib, nmf_model.joblib, and topic_labels.json "
            "into this app's folder."
        )
    else:
        user_text = st.text_area(
            "Complaint text",
            height=180,
            placeholder=(
                "e.g. I have disputed an account on my credit report three times "
                "and the bureau has not corrected the inaccurate information..."
            ),
        )

        if st.button("Classify", type="primary"):
            if not user_text.strip():
                st.warning("Please enter some complaint text first.")
            elif len(user_text.strip().split()) < 15:
                st.warning(
                    "This text is quite short. The model was trained on complaints "
                    "averaging ~93 words, so very short input can produce unreliable "
                    "predictions. Try adding more detail for a more reliable result."
                )
            else:
                X_new = vectorizer.transform([user_text])
                W_new = nmf_model.transform(X_new)[0]

                # Weight by each topic's component norm so that small, narrow
                # topics (e.g. Zelle, Cash App) don't dominate purely because
                # of scale differences in the NMF component vectors.
                topic_norms = np.linalg.norm(nmf_model.components_, axis=1)
                weighted = W_new * topic_norms

                total = weighted.sum()
                probs = weighted / total if total > 0 else weighted

                top_idx = int(np.argmax(probs))
                top_topic = top_idx + 1
                top_label = topic_labels.get(str(top_topic), f"Topic {top_topic}")

                st.success(f"**Predicted topic: {top_label}** ({probs[top_idx] * 100:.1f}% weight)")

                result_df = pd.DataFrame({
                    "Topic": [topic_labels.get(str(i + 1), f"Topic {i + 1}") for i in range(len(probs))],
                    "Weight (%)": probs * 100,
                }).sort_values("Weight (%)", ascending=True)

                fig = px.bar(
                    result_df,
                    x="Weight (%)",
                    y="Topic",
                    orientation="h",
                    title="Topic weight distribution for this complaint",
                )
                fig.update_traces(marker_color="#CFA54F")
                fig.update_layout(height=420, margin=dict(l=10, r=10, t=50, b=10))
                st.plotly_chart(fig, use_container_width=True)

                if topic_terms is not None and str(top_topic) in topic_terms:
                    st.markdown(
                        "**Top terms for this topic:** "
                        + ", ".join(topic_terms[str(top_topic)][:12])
                    )


st.markdown("---")
st.caption(
    "MSc Business Analytics · Text Analytics Group Project · Group 8 · "
    "Model: NMF, K=10, TF-IDF representation."
)