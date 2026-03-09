import os
from urllib.parse import quote_plus

import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="KG Entity Finder",
    page_icon="🔎",
    layout="wide",
)

API_URL = "https://kgsearch.googleapis.com/v1/entities:search"


def get_api_key() -> str:
    try:
        return st.secrets["GOOGLE_KG_API_KEY"]
    except Exception:
        return os.getenv("GOOGLE_KG_API_KEY", "")


def google_kg_url(kg_id: str) -> str:
    if not kg_id:
        return ""

    kgmid = kg_id.replace("kg:", "", 1)
    return f"https://www.google.com/search?kgmid={kgmid}"


def google_query_url(query: str) -> str:
    if not query:
        return ""

    return f"https://www.google.com/search?q={quote_plus(query)}"


def normalize_types(item_result: dict) -> str:
    result = item_result.get("result", {})
    types = result.get("@type", [])

    if isinstance(types, list):
        return ", ".join(types)

    if isinstance(types, str):
        return types

    return ""


def extract_description(item_result: dict) -> str:
    result = item_result.get("result", {})
    desc = result.get("description", "")

    detailed = result.get("detailedDescription", {})

    if not desc and isinstance(detailed, dict):
        desc = detailed.get("articleBody", "")

    return desc or ""


def extract_source_url(item_result: dict) -> str:
    result = item_result.get("result", {})
    detailed = result.get("detailedDescription", {})

    if isinstance(detailed, dict):
        return detailed.get("url", "") or ""

    return ""


def parse_response(data: dict) -> pd.DataFrame:
    rows = []

    for item in data.get("itemListElement", []):

        result = item.get("result", {})
        entity_name = result.get("name", "")
        kg_id = result.get("@id", "")

        rows.append(
            {
                "name": entity_name,
                "kg_id": kg_id,
                "result_score": item.get("resultScore", ""),
                "types": normalize_types(item),
                "description": extract_description(item),
                "source_url": extract_source_url(item),
                "image": result.get("image", {}).get("contentUrl", ""),
                "google_kg_url": google_kg_url(kg_id),
                "google_query_url": google_query_url(entity_name),
            }
        )

    return pd.DataFrame(rows)


def search_kg(query, api_key, limit=10, lang="pl", entity_types=None):

    params = {
        "query": query,
        "key": api_key,
        "limit": limit,
        "indent": True,
        "languages": lang,
    }

    if entity_types:
        params["types"] = entity_types

    response = requests.get(API_URL, params=params, timeout=30)
    response.raise_for_status()

    return response.json()


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def show_result_card(row: pd.Series):

    with st.container(border=True):

        left, right = st.columns([5, 1])

        with left:

            st.markdown(f"### {row['name'] or 'Brak nazwy'}")

            if row["kg_id"]:
                st.write(f"**KG ID:** `{row['kg_id']}`")

            btn1, btn2 = st.columns(2)

            with btn1:
                if row["google_kg_url"]:
                    st.link_button(
                        "🧠 Otwórz KG w Google",
                        row["google_kg_url"],
                        use_container_width=True,
                    )

            with btn2:
                if row["google_query_url"]:
                    st.link_button(
                        "🔎 Google search",
                        row["google_query_url"],
                        use_container_width=True,
                    )

            if row["types"]:
                st.write(f"**Typ:** {row['types']}")

            if row["result_score"] != "":
                st.write(f"**Score:** {row['result_score']}")

            if row["description"]:
                st.write(row["description"])

            if row["source_url"]:
                st.markdown(f"[Źródło / URL]({row['source_url']})")

        with right:
            if row["image"]:
                st.image(row["image"], use_container_width=True)


st.title("🔎 KG Entity Finder")
st.caption("Wyszukiwarka encji Google Knowledge Graph")

api_key = get_api_key()

with st.sidebar:

    st.header("Ustawienia")

    query = st.text_input(
        "Fraza / encja",
        placeholder="np. Robert Marczak, Google, OpenAI, Warsaw",
    )

    lang = st.selectbox(
        "Język",
        options=["pl", "en", "de", "fr", "es", "it", "nl", "cs", "sk", "ro", "hu"],
        index=0,
    )

    limit = st.slider("Liczba wyników", 1, 20, 10)

    type_options = [
        "Person",
        "Organization",
        "Place",
        "LocalBusiness",
        "Corporation",
        "Thing",
        "Event",
        "CreativeWork",
        "Article",
        "Product",
    ]

    selected_types = st.multiselect(
        "Typ encji (opcjonalnie)",
        options=type_options,
    )

    search_btn = st.button("Szukaj", type="primary", use_container_width=True)


if not api_key:
    st.error(
        "Brakuje klucza API. Dodaj GOOGLE_KG_API_KEY do `.streamlit/secrets.toml`"
    )
    st.stop()


if search_btn:

    with st.spinner("Szukam encji w Google Knowledge Graph..."):

        data = search_kg(
            query=query,
            api_key=api_key,
            limit=limit,
            lang=lang,
            entity_types=selected_types if selected_types else None,
        )

    df = parse_response(data)

    st.subheader("Wyniki")

    if df.empty:
        st.warning("Brak wyników.")
    else:

        left, right = st.columns([3, 1])

        with left:
            st.dataframe(
                df[
                    [
                        "name",
                        "kg_id",
                        "types",
                        "result_score",
                        "google_kg_url",
                        "google_query_url",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "google_kg_url": st.column_config.LinkColumn(
                        "KG w Google",
                        display_text="Otwórz",
                    ),
                    "google_query_url": st.column_config.LinkColumn(
                        "Google",
                        display_text="Szukaj",
                    ),
                },
            )

        with right:

            st.metric("Liczba wyników", len(df))

            st.download_button(
                "Pobierz CSV",
                data=to_csv_bytes(df),
                file_name=f"kg_results_{query}.csv",
                mime="text/csv",
                use_container_width=True,
            )

        st.subheader("Podgląd encji")

        for _, row in df.iterrows():
            show_result_card(row)


# ---------------------------------------------------
# FOOTER
# ---------------------------------------------------

st.markdown("---")

col1, col2, col3 = st.columns([3,1,3])

with col2:

    st.markdown(
        """
        <div style="text-align:center">
            <a href="https://marczak.me" target="_blank">
                <img src="https://marczak.me/media/website/marczakme-logo-mniejsze-2.png" width="120">
            </a>
        </div>
        """,
        unsafe_allow_html=True
    )
