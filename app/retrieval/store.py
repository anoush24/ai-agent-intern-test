import json
from pathlib import Path

import numpy as np

from app.models.schemas import Chunk, RetrievedChunk
from app.retrieval.embedder import embed_query


class ChunkStore:
    
    def __init__(self, persist_dir: str | None = None):
        self.persist_dir = Path(
            persist_dir or "./index"
        )

        self.vectors_path = self.persist_dir / "vectors.npy"
        self.metadata_path = self.persist_dir / "metadata.json"

        self.persist_dir.mkdir(parents=True, exist_ok=True)

    def rebuild_collection(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> None:
       

        if len(chunks) != len(embeddings):
            raise ValueError(
                "Number of chunks must match number of embeddings."
            )

        vectors = np.asarray(embeddings, dtype=np.float32)

        if vectors.ndim != 2:
            raise ValueError("Embeddings must be a 2D array.")

        np.save(self.vectors_path, vectors)

        metadata = [
            {
                "id": chunk.id,
                "text": chunk.text,
                "source_file": chunk.source_file,
                "heading": chunk.heading,
                "document_id": chunk.document_id,
                "status": chunk.status,
                "policy_authority": chunk.policy_authority,
                "superseded_by": chunk.superseded_by,
                "audience": chunk.audience,
                "customer_answering": chunk.customer_answering,
                "doc_title": chunk.doc_title,
            }
            for chunk in chunks
        ]

        self.metadata_path.write_text(
            json.dumps(metadata, indent=2),
            encoding="utf-8",
        )

    def query(
        self,
        query_text: str,
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        

        if not self.vectors_path.exists() or not self.metadata_path.exists():
            raise FileNotFoundError(
                "Vector index not found. Build the index first."
            )

        vectors = np.load(self.vectors_path)

        metadata = json.loads(
            self.metadata_path.read_text(encoding="utf-8")
        )

        if len(vectors) != len(metadata):
            raise ValueError(
                "Vector and metadata counts do not match."
            )

        query_vector = np.asarray(
            embed_query(query_text),
            dtype=np.float32,
        )

        # Cosine similarity
        vector_norms = np.linalg.norm(vectors, axis=1)
        query_norm = np.linalg.norm(query_vector)

        if query_norm == 0:
            raise ValueError("Query embedding has zero magnitude.")

        similarities = (
            vectors @ query_vector
        ) / (
            vector_norms * query_norm
        )

        top_k = min(top_k, len(similarities))

        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []

        for index in top_indices:
            meta = metadata[index]

            chunk = Chunk(
                id=meta["id"],
                text=meta["text"],
                source_file=meta["source_file"],
                heading=meta["heading"],
                document_id=meta.get("document_id"),
                status=meta.get("status", "active"),
                policy_authority=meta.get("policy_authority"),
                superseded_by=meta.get("superseded_by"),
                audience=meta.get("audience"),
                customer_answering=meta.get(
                    "customer_answering",
                    True,
                ),
                doc_title=meta.get("doc_title"),
            )

            results.append(
                RetrievedChunk(
                    chunk=chunk,
                    score=float(similarities[index]),
                )
            )

        return results