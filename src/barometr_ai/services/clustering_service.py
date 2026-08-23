"""Semantyczna deduplikacja i klastrowanie strumienia dokumentów."""

import hashlib

import numpy as np

from barometr_ai.domain.models import ClusterGroup, ClusterRequest, ClusterResponse
from barometr_ai.ports.embedder import EmbedderPort


class ClusteringService:
    """Odpowiada za deduplikację zduplikowanych depesz i grupowanie w klastry tematyczne."""

    def __init__(self, embedder: EmbedderPort) -> None:
        self._embedder = embedder

    def cluster_documents(self, request: ClusterRequest) -> ClusterResponse:
        """Grupuje dokumenty na podstawie dokładnego hasha oraz podobieństwa wektorowego."""
        docs = request.documents
        if not docs:
            return ClusterResponse(clusters=[], reduction_rate=0.0, total_processed=0)

        # 1. Krok 1: Wstępna deduplikacja po hashu znormalizowanego tekstu (L1)
        content_to_docs: dict[str, list[str]] = {}
        unique_docs = []

        for doc in docs:
            norm_content = " ".join(doc.content.lower().split())
            content_hash = hashlib.sha256(norm_content.encode("utf-8")).hexdigest()
            if content_hash not in content_to_docs:
                content_to_docs[content_hash] = []
                unique_docs.append(doc)
            content_to_docs[content_hash].append(doc.id)

        # 2. Krok 2: Embeddingi dla unikalnych dokumentów (L2)
        texts = [d.content for d in unique_docs]
        vectors = self._embedder.embed_texts(texts, normalize=True)

        # 3. Krok 3: Klastrowanie semantyczne (online centroid assignment)
        clusters: list[ClusterGroup] = []
        assigned = [False] * len(unique_docs)

        for i in range(len(unique_docs)):
            if assigned[i]:
                continue

            current_doc = unique_docs[i]
            current_vec = np.array(vectors[i])
            cluster_members = list(
                content_to_docs[
                    hashlib.sha256(
                        " ".join(current_doc.content.lower().split()).encode("utf-8")
                    ).hexdigest()
                ]
            )
            assigned[i] = True

            similarities = [1.0]

            for j in range(i + 1, len(unique_docs)):
                if assigned[j]:
                    continue
                other_vec = np.array(vectors[j])
                similarity = float(np.dot(current_vec, other_vec))
                if similarity >= request.threshold:
                    other_doc = unique_docs[j]
                    other_hash = hashlib.sha256(
                        " ".join(other_doc.content.lower().split()).encode("utf-8")
                    ).hexdigest()
                    cluster_members.extend(content_to_docs[other_hash])
                    similarities.append(similarity)
                    assigned[j] = True

            cluster_id = f"cls_{hashlib.md5(current_doc.id.encode('utf-8')).hexdigest()[:8]}"
            clusters.append(
                ClusterGroup(
                    cluster_id=cluster_id,
                    representative_document_id=current_doc.id,
                    member_document_ids=sorted(set(cluster_members)),
                    cohesion_score=round(float(np.mean(similarities)), 3),
                )
            )

        total_input = len(docs)
        total_clusters = len(clusters)
        reduction = (total_input - total_clusters) / total_input if total_input > 0 else 0.0

        return ClusterResponse(
            clusters=clusters,
            reduction_rate=round(reduction, 2),
            total_processed=total_input,
        )
