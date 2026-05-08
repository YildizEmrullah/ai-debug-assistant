import os
from html import escape

import streamlit as st
from dotenv import load_dotenv

from services.ai_service import AIServiceError, analyze_error_with_ai
from services.error_parser import parse_error
from services.history_db import (
    clear_history,
    count_history,
    fetch_analysis,
    fetch_history,
    init_db,
    save_analysis,
)
from services.rag_service import build_rag_pipeline, retrieve_similar_chunks


load_dotenv()
init_db()

st.set_page_config(
    page_title="AI Debug Assistant",
    layout="wide",
)

DEMO_ERRORS = {
    "TypeError": """TypeError: Cannot read properties of undefined (reading 'map')
    at UserList (src/components/UserList.jsx:18:21)
    at renderWithHooks (react-dom.development.js:16305:18)""",
    "NameError": """Traceback (most recent call last):
  File "app.py", line 22, in <module>
    print(user_name)
NameError: name 'user_name' is not defined""",
    "IndexError": """Traceback (most recent call last):
  File "report.py", line 14, in build_report
    first_item = items[0]
IndexError: list index out of range""",
    "ModuleNotFoundError": """Traceback (most recent call last):
  File "app.py", line 4, in <module>
    import requests
ModuleNotFoundError: No module named 'requests'""",
}


st.markdown(
    """
    <style>
    .block-container {
        max-width: 1280px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }
    div[data-testid="stHorizontalBlock"] {
        gap: 1rem;
    }
    .metric-card {
        border: 1px solid #dbe3ef;
        border-radius: 14px;
        min-height: 104px;
        padding: 1.05rem 1.15rem;
        background: linear-gradient(135deg, #ffffff 0%, #f7fafc 58%, #edf7f3 100%);
        box-shadow: 0 14px 34px rgba(15, 23, 42, 0.08);
    }
    .metric-card span {
        display: block;
        color: #64748b;
        font-size: 0.85rem;
        font-weight: 700;
    }
    .metric-card strong {
        display: block;
        color: #0f172a;
        font-size: 1.55rem;
        margin-top: 0.25rem;
    }
    .analysis-card {
        border: 1px solid #dbe3ef;
        border-left: 5px solid #0f766e;
        border-radius: 14px;
        padding: 1rem 1.15rem;
        background: #ffffff;
        box-shadow: 0 10px 26px rgba(15, 23, 42, 0.06);
        margin-bottom: 0.85rem;
    }
    .analysis-card h4 {
        margin: 0 0 0.55rem 0;
        color: #0f172a;
    }
    .analysis-card p {
        margin-bottom: 0;
        color: #334155;
        line-height: 1.55;
    }
    .mode-pill {
        display: inline-block;
        padding: 0.35rem 0.65rem;
        border-radius: 999px;
        background: #ecfdf5;
        color: #047857;
        font-size: 0.8rem;
        font-weight: 800;
        border: 1px solid #a7f3d0;
    }
    .section-label {
        color: #475569;
        font-size: 0.8rem;
        font-weight: 800;
        text-transform: uppercase;
    }
    .app-badge {
        display: inline-block;
        margin-bottom: 0.65rem;
        padding: 0.4rem 0.75rem;
        border-radius: 999px;
        color: #0f766e;
        background: #ecfdf5;
        border: 1px solid #99f6e4;
        font-size: 0.82rem;
        font-weight: 900;
    }
    .footer {
        margin-top: 2.5rem;
        padding: 1rem 0 0;
        border-top: 1px solid #e2e8f0;
        color: #64748b;
        font-size: 0.9rem;
        text-align: center;
    }
    @media (max-width: 900px) {
        .metric-card {
            min-height: auto;
            margin-bottom: 0.65rem;
        }
        .analysis-card {
            padding: 0.95rem;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def read_sample_errors() -> str:
    try:
        with open("sample_errors.txt", "r", encoding="utf-8") as file:
            return file.read().strip()
    except FileNotFoundError:
        return ""


@st.cache_resource(show_spinner=False)
def get_rag_pipeline():
    return build_rag_pipeline()


def format_regex_summary(parsed_error) -> str:
    frames = format_stack_frames(parsed_error)
    suggestions = "\n".join(f"- {item}" for item in parsed_error.suggestions)

    return f"""### Regex On Analizi

**Hata Türü:** {parsed_error.error_type or "Belirlenemedi"}

**Özet:** {parsed_error.short_message or "Hata mesaji ayristirilamadi."}

**Olasi kategori:** {parsed_error.category}

**Bulunan konumlar:**
{frames}

**İlk kontrol önerileri:**
{suggestions}
"""


def format_stack_frames(parsed_error) -> str:
    frame_lines = [
        f"- {frame.file_path}:{frame.line_number} in {frame.function_name or 'unknown'}"
        for frame in parsed_error.stack_frames[:5]
    ]
    return "\n".join(frame_lines) if frame_lines else "- Stack frame bulunamadi."


def format_rag_summary(rag_chunks):
    if not rag_chunks:
        return "Retriever sonucu bulunamadi veya RAG pipeline hazir degil."

    lines = []
    for chunk in rag_chunks:
        lines.append(f"### Chunk {chunk.index} - skor {chunk.score:.3f}\n{chunk.text}")
    return "\n\n".join(lines)


def get_local_analysis(parsed_error):
    category = parsed_error.category.lower()
    error_type = (parsed_error.error_type or "").lower()

    if "null" in category or "undefined" in category or "typeerror" in error_type:
        return {
            "probable_cause": "Veri henuz gelmeden veya bos/undefined durumdayken liste metodu ya da ozellik erisimi yapiliyor.",
            "solution": [
                "Degeri kullanmadan once null/undefined kontrolu ekle.",
                "Liste beklenen alanlar icin varsayilan degeri bos liste yap.",
                "API verisi yuklenene kadar loading veya fallback UI goster.",
            ],
            "fixed_code": """const users = response?.users ?? [];

return users.map((user) => (
  <UserCard key={user.id} user={user} />
));""",
        }

    if "tanimlanmamis" in category or "nameerror" in error_type:
        return {
            "probable_cause": "Kod, tanimlanmamis veya yanlis scope icindeki bir degisken/fonksiyon adina erisiyor.",
            "solution": [
                "Degisken adinin dogru yazildigini kontrol et.",
                "Degiskeni kullanmadan once ayni scope icinde tanimla.",
                "Gerekliyse eksik import satirini ekle.",
            ],
            "fixed_code": """user_name = "Ayse"
print(user_name)""",
        }

    if "indeks" in category or "indexerror" in error_type:
        return {
            "probable_cause": "Liste bosken veya indeks listenin uzunlugunu astiginda elemana erisilmeye calisiliyor.",
            "solution": [
                "Listeye erismeden once eleman sayisini kontrol et.",
                "Bos liste icin ayri bir mesaj veya fallback deger kullan.",
                "Dongu sinirlarini ve hesaplanan indeks degerlerini dogrula.",
            ],
            "fixed_code": """if items:
    first_item = items[0]
else:
    first_item = None""",
        }

    if "import" in category or "modulenotfounderror" in error_type:
        return {
            "probable_cause": "Gerekli paket kurulu degil, sanal ortam aktif degil veya uygulama farkli Python ortamindan calisiyor.",
            "solution": [
                "Paketi requirements.txt dosyasina ekle.",
                "Sanal ortami aktif edip paketi yukle.",
                "Uygulamayi dogru proje klasorunden calistir.",
            ],
            "fixed_code": """# requirements.txt
requests>=2.32.0

# terminal
pip install -r requirements.txt""",
        }

    if "sozdizimi" in category:
        return {
            "probable_cause": "Kodda kapanmayan parantez, eksik tirnak veya beklenmeyen karakter bulunuyor.",
            "solution": [
                "Hata satirindan bir onceki satiri da kontrol et.",
                "Formatter/linter calistir.",
                "Parantez, koseli parantez ve tirnak eslesmelerini gozden gecir.",
            ],
            "fixed_code": """config = {
    "debug": True,
    "retries": 3,
}""",
        }

    return {
        "probable_cause": "Hata metni genel bir sorun isaret ediyor; ilk proje dosyasi ve ilgili satir incelenmeli.",
        "solution": parsed_error.suggestions,
        "fixed_code": """# 1. Stack trace icindeki ilk proje dosyasini ac
# 2. Ilgili satirdaki degiskenleri logla
# 3. Hatayi kucuk bir ornekle tekrar uret""",
    }


def render_metric(label, value):
    st.markdown(
        f"""
        <div class="metric-card">
            <span>{escape(str(label))}</span>
            <strong>{escape(str(value))}</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_text_card(title, body):
    st.markdown(
        f"""
        <div class="analysis-card">
            <h4>{escape(str(title))}</h4>
            <p>{escape(str(body))}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_saved_summary(parsed_error, local_analysis, analysis_text, analysis_mode, rag_chunks):
    probable_cause = local_analysis["probable_cause"]
    fixed_code = local_analysis["fixed_code"]
    solutions = "\n".join(f"- {item}" for item in local_analysis["solution"])
    rag_summary = format_rag_summary(rag_chunks)
    return f"""## {analysis_mode}

### Hata Türü
{parsed_error.error_type or "Belirlenemedi"} - {parsed_error.category}

### Özet
{parsed_error.short_message or "Hata mesaji ayristirilamadi."}

### Muhtemel Sebep
{probable_cause}

### Çözüm Önerileri
{solutions}

### Düzeltilmiş Kod Örneği
```text
{fixed_code}
```

### Analiz Sonucu
{analysis_text}

### RAG Retriever Sonucu
{rag_summary}
"""


def render_rag_chunks(rag_chunks):
    with st.container(border=True):
        st.markdown("#### Retriever Sonucu")
        if not rag_chunks:
            st.info("Benzer knowledge chunk bulunamadi. RAG pipeline pasif veya sorgu bos olabilir.")
            return

        for chunk in rag_chunks:
            with st.expander(f"Knowledge Chunk {chunk.index} | Benzerlik skoru: {chunk.score:.3f}"):
                st.write(chunk.text)


def render_analysis_cards(parsed_error, local_analysis, analysis_text, analysis_mode, rag_chunks):
    st.markdown(f'<span class="mode-pill">{analysis_mode}</span>', unsafe_allow_html=True)
    st.write("")

    type_col, category_col = st.columns(2)
    with type_col:
        render_metric("Hata Türü", parsed_error.error_type or "Belirlenemedi")
    with category_col:
        render_metric("Kategori", parsed_error.category)

    render_text_card("Özet", parsed_error.short_message or "Hata mesaji ayristirilamadi.")
    render_text_card("Muhtemel Sebep", local_analysis["probable_cause"])

    with st.container(border=True):
        st.markdown("#### Çözüm Önerileri")
        for suggestion in local_analysis["solution"]:
            st.markdown(f"- {suggestion}")

    with st.container(border=True):
        st.markdown("#### Düzeltilmiş Kod Örneği")
        st.code(local_analysis["fixed_code"], language="text")

    with st.container(border=True):
        st.markdown("#### Regex Sonucu")
        st.markdown(format_regex_summary(parsed_error))

    with st.container(border=True):
        st.markdown("#### Analiz Sonucu")
        st.markdown(analysis_text)

    render_rag_chunks(rag_chunks)

    with st.expander("Bulunan dosya ve satirlar", expanded=bool(parsed_error.stack_frames)):
        st.markdown(format_stack_frames(parsed_error))


def render_history_detail(item):
    st.markdown("### Geçmiş Kayıt Detayı")
    meta_col_1, meta_col_2, meta_col_3 = st.columns(3)
    with meta_col_1:
        render_metric("Hata Türü", item.get("error_type") or "Belirlenemedi")
    with meta_col_2:
        render_metric("Kategori", item.get("category") or "Genel")
    with meta_col_3:
        render_metric("Tarih/Saat", item.get("created_at") or "-")

    st.markdown("#### Özet")
    st.info(item.get("title") or "Hata analizi")

    with st.expander("Kullanıcı girdisi", expanded=True):
        st.code(item.get("error_text") or "", language="text")

    with st.expander("Analiz sonucu", expanded=True):
        st.markdown(item.get("summary") or "")


st.markdown('<span class="app-badge">Mini-RAG Debug System</span>', unsafe_allow_html=True)
st.title("AI Debug Assistant")
st.caption("Python, Streamlit, OpenAI API, SQLite ve Regex ile hata analizi.")

rag_pipeline = get_rag_pipeline()
history_items = fetch_history(limit=25)
history_count = count_history()
latest_date = history_items[0]["created_at"] if history_items else "-"

metric_col_1, metric_col_2, metric_col_3 = st.columns(3)
with metric_col_1:
    render_metric("Toplam Geçmiş", history_count)
with metric_col_2:
    render_metric("Son Analiz", latest_date)
with metric_col_3:
    render_metric("Demo Hata Tipi", len(DEMO_ERRORS))

st.markdown("### RAG Pipeline Durumu")
rag_col_1, rag_col_2, rag_col_3, rag_col_4 = st.columns(4)
with rag_col_1:
    pipeline_label = "Hazir" if rag_pipeline.is_ready else "Pasif"
    render_metric("Pipeline", pipeline_label)
with rag_col_2:
    render_metric("Chunk Sayisi", rag_pipeline.chunk_count)
with rag_col_3:
    render_metric("Embedding Modeli", rag_pipeline.embedding_model)
with rag_col_4:
    render_metric("Vector DB", rag_pipeline.vector_db if rag_pipeline.is_ready else rag_pipeline.status)

if rag_pipeline.error:
    st.warning(f"RAG pipeline uyarisi: {rag_pipeline.error}")

with st.sidebar:
    st.header("Ayarlar")
    model = st.text_input("OpenAI model", value=os.getenv("OPENAI_MODEL", "gpt-5.4-mini"))
    use_ai = st.toggle("OpenAI ile analiz et", value=True)
    if use_ai:
        st.caption("Mod: OpenAI destekli gelismis analiz")
    else:
        st.caption("Mod: Yerel Regex Analizi")
    st.divider()
    st.subheader("Sistem Bilgisi")
    st.write("**Etiket:** Mini-RAG Debug System")
    st.write(f"**Kullanılan model:** {model if use_ai else 'Yerel TF-IDF + Regex'}")
    st.write(f"**RAG durumu:** {'Aktif' if rag_pipeline.is_ready else 'Pasif'}")
    st.write(f"**Chunk sayısı:** {rag_pipeline.chunk_count}")
    st.write(f"**Retrieval tipi:** {rag_pipeline.vector_db}")
    st.divider()
    st.subheader("Geçmiş")
    if not history_items:
        st.info("Henüz kayıt yok.")
        selected_history_id = None
    else:
        history_options = {
            f'{item["created_at"]} - {item["title"][:48]}': item["id"]
            for item in history_items
        }
        selected_history_label = st.selectbox("Kayıt seç", list(history_options.keys()))
        selected_history_id = history_options[selected_history_label]

        if st.button("Geçmişi temizle", use_container_width=True):
            clear_history()
            st.session_state.selected_history_id = None
            st.rerun()

sample_text = read_sample_errors()

left, right = st.columns([1.0, 1.0], gap="large")

with left:
    st.markdown("### Hata Girdisi")
    if "error_input" not in st.session_state:
        st.session_state.error_input = ""

    st.markdown('<div class="section-label">Demo Hatalar</div>', unsafe_allow_html=True)
    demo_cols = st.columns(4)
    for index, (label, demo_error) in enumerate(DEMO_ERRORS.items()):
        with demo_cols[index]:
            if st.button(label, use_container_width=True):
                st.session_state.error_input = demo_error

    if st.button("Tüm örnekleri yükle", use_container_width=True):
        st.session_state.error_input = sample_text

    error_text = st.text_area(
        "Stack trace veya hata mesajı",
        key="error_input",
        height=360,
        placeholder="TypeError, traceback, build error veya test ciktisini buraya yapistir...",
    )

    analyze_clicked = st.button("Analiz et", type="primary", use_container_width=True)

with right:
    st.markdown("### Analiz Sonucu")

    if analyze_clicked:
        if not error_text.strip():
            st.warning("Lütfen analiz edilecek bir hata metni gir.")
        else:
            parsed_error = parse_error(error_text)
            regex_summary = format_regex_summary(parsed_error)
            local_analysis = get_local_analysis(parsed_error)
            rag_query = f"{parsed_error.error_type} {parsed_error.category}\n{error_text}"
            rag_chunks = retrieve_similar_chunks(rag_pipeline, rag_query, top_k=3)
            analysis_mode = "Yerel Regex Analizi"

            final_analysis = regex_summary
            if use_ai:
                try:
                    with st.spinner("OpenAI analizi hazirlaniyor..."):
                        ai_analysis = analyze_error_with_ai(
                            raw_error=error_text,
                            parsed_error=parsed_error,
                            model=model,
                            rag_chunks=rag_chunks,
                        )
                    final_analysis = ai_analysis
                    analysis_mode = "OpenAI Destekli Analiz"
                except AIServiceError as exc:
                    st.error(str(exc))
                    st.info("OpenAI cagrisi basarisiz olsa bile regex on analizi kullanilabilir.")

            saved_summary = build_saved_summary(
                parsed_error=parsed_error,
                local_analysis=local_analysis,
                analysis_text=final_analysis,
                analysis_mode=analysis_mode,
                rag_chunks=rag_chunks,
            )
            render_analysis_cards(
                parsed_error,
                local_analysis,
                final_analysis,
                analysis_mode,
                rag_chunks,
            )

            save_analysis(
                title=parsed_error.short_message or "Hata analizi",
                error_text=error_text,
                summary=saved_summary,
                error_type=parsed_error.error_type,
                category=parsed_error.category,
            )
            st.success("Analiz gecmise kaydedildi.")
    else:
        st.info("Hata metnini girip analizi baslat veya soldaki demo hata butonlarindan birini sec.")

if selected_history_id:
    st.divider()
    selected_item = fetch_analysis(selected_history_id)
    if selected_item:
        render_history_detail(selected_item)

st.markdown(
    """
    <div class="footer">
        AI Debug Assistant · Mini-RAG Debug System · Regex + TF-IDF + SQLite + Streamlit
    </div>
    """,
    unsafe_allow_html=True,
)
