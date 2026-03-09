import io
import os
import requests
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="KG Entity Finder",
    page_icon="🔎",
    layout="wide",
)

API_URL = "https://kgsearch.googleapis.com/v1/entities:search"


def get_api_key() -> str:
    """
    Reads API key from Streamlit secrets first, then environment variable.
    """
    api_key = None

    try:
        api_key = st.secrets["GOOGLE_KG_API_KEY"]
    except Exception:
        api_key = os.getenv("GOOGLE_KG_API_KEY")

    return api_key or ""


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


def extract_url(item_result: dict) -> str:
    result = item_result.get("result", {})
    detailed = result.get("detailedDescription", {})
    if isinstance(detailed, dict):
        return detailed.get("url", "") or ""
    return ""


def parse_response(data: dict) -> pd.DataFrame:
    rows = []

    for item in data.get("itemListElement", []):
        result = item.get("result", {})

        rows.append(
            {
                "name": result.get("name", ""),
                "kg_id": result.get("@id", ""),
                "result_score": item.get("resultScore", ""),
                "types": normalize_types(item),
                "description": extract_description(item),
                "url": extract_url(item),
                "image": result.get("image", {}).get("contentUrl", ""),
            }
        )

    return pd.DataFrame(rows)


def search_kg(
    query: str,
    api_key: str,
    limit: int = 10,
    lang: str = "pl",
    entity_types: list[str] | None = None,
) -> dict:
    """
    Calls Google Knowledge Graph Search API.
    """
    params = {
        "query": query,
        "key": api_key,
        "limit": limit,
        "indent": True,
        "languages": lang,
    }

    if entity_types:
        # API allows repeated types params
        params["types"] = entity_types

    response = requests.get(API_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


st.title("🔎 KG Entity Finder")
st.caption("Wyszukiwarka encji Google Knowledge Graph pod GitHub + Streamlit")

api_key = get_api_key()

with st.sidebar:
    st.header("Ustawienia")

    query = st.text_input(
        "Fraza / encja",
        placeholder="np. Robert Marczak, Google, Warsaw, OpenAI",
    )

    lang = st.selectbox(
        "Język",
        options=["pl", "en", "de", "fr", "es", "it", "nl", "cs", "sk", "ro", "hu"],
        index=0,
    )

    limit = st.slider("Liczba wyników", min_value=1, max_value=20, value=10)

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
        default=[],
    )

    search_btn = st.button("Szukaj", type="primary", use_container_width=True)

if not api_key:
    st.error(
        "Brakuje klucza API. Dodaj GOOGLE_KG_API_KEY do `.streamlit/secrets.toml` "
        "lub jako zmienną środowiskową."
    )
    st.stop()

if not query and not search_btn:
    st.info("Wpisz nazwę encji po lewej stronie i kliknij „Szukaj”.")
    st.stop()

if search_btn:
    try:
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
            st.warning("Brak wyników dla podanego zapytania.")
        else:
            col1, col2 = st.columns([3, 1])

            with col1:
                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True,
                )

            with col2:
                st.metric("Liczba wyników", len(df))

                st.download_button(
                    label="Pobierz CSV",
                    data=to_csv_bytes(df),
                    file_name=f"kg_results_{query.strip().replace(' ', '_')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            st.subheader("Podgląd kart")

            for _, row in df.iterrows():
                with st.container(border=True):
                    left, right = st.columns([5, 1])

                    with left:
                        st.markdown(f"### {row['name'] or 'Brak nazwy'}")
                        st.write(f"**KG ID:** `{row['kg_id']}`")
                        if row["types"]:
                            st.write(f"**Typ:** {row['types']}")
                        if row["result_score"] != "":
                            st.write(f"**Score:** {row['result_score']}")
                        if row["description"]:
                            st.write(row["description"])
                        if row["url"]:
                            st.markdown(f"[Źródło / URL]({row['url']})")

                    with right:
                        if row["image"]:
                            st.image(row["image"], use_container_width=True)

            with st.expander("Surowa odpowiedź JSON"):
                st.json(data)

    except requests.HTTPError as e:
        st.error(f"Błąd HTTP: {e}")
        try:
            st.json(e.response.json())
        except Exception:
            st.write("Nie udało się odczytać odpowiedzi błędu.")
    except requests.RequestException as e:
        st.error(f"Błąd połączenia: {e}")
    except Exception as e:
        st.error(f"Nieoczekiwany błąd: {e}")
