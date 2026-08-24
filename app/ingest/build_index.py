from pathlib import Path
from app.ingest.loader import load_documents
from app.ingest.chunker import chunk_document
from app.retrieval.embedder import embed_texts
from app.retrieval.store import ChunkStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]
KB_DIR = PROJECT_ROOT / "knowledge-base"
INDEX_DIR = PROJECT_ROOT / "index"


def build_index():
    documents = load_documents(KB_DIR)
    print(f"Loaded {len(documents)} documents")

    all_chunks = []

    for document in documents:
        all_chunks.extend(chunk_document(document))

    print(f"Produced {len(all_chunks)} chunks")

    texts = [chunk.text for chunk in all_chunks]

    embeddings = embed_texts(texts)

    print(f"Embedded {len(embeddings)} chunks")

    store = ChunkStore(
        persist_dir=str(INDEX_DIR)
    )

    store.rebuild_collection(
        chunks=all_chunks,
        embeddings=embeddings,
    )

    print(f"Index built at {INDEX_DIR}")


if __name__ == "__main__":
    build_index()