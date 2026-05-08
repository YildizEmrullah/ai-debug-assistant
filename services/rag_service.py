from dataclasses import dataclass
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


EMBEDDING_MODEL_NAME = "TF-IDF"
VECTOR_DB_NAME = "sklearn cosine similarity"
KNOWLEDGE_BASE_PATH = Path(__file__).resolve().parent.parent / "errors_knowledge_base.txt"


@dataclass
class RagChunk:
    index: int
    text: str
    score: float = 0.0


@dataclass
class RagPipeline:
    status: str
    chunk_count: int
    embedding_model: str
    vector_db: str
    chunks: list[RagChunk]
    vectorizer: TfidfVectorizer | None = None
    matrix: object = None
    error: str = ""

    @property
    def is_ready(self):
        return self.status == "ready" and self.vectorizer is not None and self.matrix is not None


def read_knowledge_base(path=KNOWLEDGE_BASE_PATH):
    return Path(path).read_text(encoding="utf-8")


def chunk_text(text, min_size=300, max_size=500):
    blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
    chunks = []
    current = ""

    for block in blocks:
        candidate = f"{current}\n\n{block}".strip() if current else block
        if len(candidate) <= max_size:
            current = candidate
            continue

        if current:
            chunks.append(current)
        current = block

        while len(current) > max_size:
            split_at = current.rfind("\n", 0, max_size)
            if split_at < min_size:
                split_at = max_size
            chunks.append(current[:split_at].strip())
            current = current[split_at:].strip()

    if current:
        chunks.append(current)

    merged = []
    for chunk in chunks:
        if merged and len(chunk) < min_size and len(merged[-1]) + len(chunk) + 2 <= max_size:
            merged[-1] = f"{merged[-1]}\n\n{chunk}"
        else:
            merged.append(chunk)

    return [RagChunk(index=index, text=chunk) for index, chunk in enumerate(merged, start=1)]


def build_rag_pipeline():
    try:
        text = read_knowledge_base()
        chunks = chunk_text(text)
        vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            ngram_range=(1, 2),
        )
        matrix = vectorizer.fit_transform([chunk.text for chunk in chunks])

        return RagPipeline(
            status="ready",
            chunk_count=len(chunks),
            embedding_model=EMBEDDING_MODEL_NAME,
            vector_db=VECTOR_DB_NAME,
            chunks=chunks,
            vectorizer=vectorizer,
            matrix=matrix,
        )
    except Exception as exc:
        return RagPipeline(
            status="error",
            chunk_count=0,
            embedding_model=EMBEDDING_MODEL_NAME,
            vector_db=VECTOR_DB_NAME,
            chunks=[],
            error=str(exc),
        )


def retrieve_similar_chunks(pipeline, query, top_k=3):
    if not pipeline.is_ready or not query.strip():
        return []

    query_vector = pipeline.vectorizer.transform([query])
    scores = cosine_similarity(query_vector, pipeline.matrix).flatten()
    ranked_indexes = scores.argsort()[::-1][:top_k]

    return [
        RagChunk(
            index=pipeline.chunks[int(chunk_index)].index,
            text=pipeline.chunks[int(chunk_index)].text,
            score=float(scores[int(chunk_index)]),
        )
        for chunk_index in ranked_indexes
    ]
