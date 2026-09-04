"""Semantyczna deduplikacja i klastrowanie strumienia dokumentów (warstwa L1 kaskady).

Dwie warstwy:

1. **Odcisk dokładny** — SHA-256 tekstu znormalizowanego przez zniesienie wielkości liter,
   interpunkcji i odstępów. Scala wyłącznie to, czego rozdzielenie jest bezsporną pomyłką.
2. **Klastrowanie semantyczne** — aglomeracja o średnim wiązaniu na embeddingach.

Wynik nie zależy od kolejności dokumentów w żądaniu: aglomeracja łączy w każdym kroku
globalnie najbardziej podobną parę, a nie parę napotkaną jako pierwsza.

Świadomie **nie ma** tu warstwy near-duplicate na SimHashu ani MinHashu, choć audyt ją
zalecał. Pomiar na wariantach depesz PL (ADR 0003) pokazał, że dla tekstów tej długości
pasma się nakładają: przedruk z dopisanym podpisem redakcji daje Jaccard 0,912, a ten sam
szablon z podmienionym przedmiotem regulacji 0,878 — natomiast zmiana „obejmą" na
„nie obejmą" daje 0,955, czyli wygląda na duplikat bliższy niż jakikolwiek prawdziwy
przedruk. Każdy próg leksykalny sklejałby więc dokumenty o przeciwnym znaczeniu i wysyłał
do streszczenia tylko jeden z nich. Rozdzielenie takich par wymaga porównania twierdzeń,
nie pokrycia leksykalnego.
"""

import hashlib
import re

import numpy as np
from numpy.typing import NDArray

from barometr_ai.core.exceptions import InvalidDocumentBatchError
from barometr_ai.domain.models import (
    ClusterGroup,
    ClusterRequest,
    ClusterResponse,
    DocumentItem,
)
from barometr_ai.ports.embedder import EmbedderPort

#: Aglomeracja utrzymuje macierz podobieństw n×n (float64). 512 dokumentów to ok. 2 MB,
#: 10 000 to już 800 MB, czyli awaria workera. Wsad ponad limit musi pokroić wywołujący —
#: cichy sampling zafałszowałby `reduction_rate`, który jest miarą kosztową całej kaskady.
MAX_DOCUMENTS = 512

#: Poniżej tej normy wektor uznajemy za zerowy — podobieństwo kosinusowe jest nieokreślone.
_MIN_VECTOR_NORM = 1e-9

#: Wszystko, co nie jest literą, cyfrą ani odstępem. Interpunkcja i myślniki redakcyjne
#: różnią się między przedrukami tej samej depeszy, a nie niosą treści normatywnej.
_PUNCTUATION = re.compile(r"[^\w\s]", flags=re.UNICODE)


def normalize_text(text: str) -> str:
    """Kanonizuje tekst do porównań: małe litery, bez interpunkcji, pojedyncze odstępy.

    Zniesienie interpunkcji jest celowo jedynym rozluźnieniem względem porównania znak w
    znak. Każde dalsze — zniesienie liczb, dat czy krótkich słów — sklejałoby dokumenty
    różniące się treścią normatywną.
    """
    return " ".join(_PUNCTUATION.sub(" ", text.lower()).split())


def content_fingerprint(text: str) -> str:
    """Odcisk dokładny znormalizowanego tekstu."""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


class ClusteringService:
    """Grupuje strumień dokumentów, odcinając duplikaty przed warstwami płatnymi."""

    def __init__(self, embedder: EmbedderPort) -> None:
        self._embedder = embedder

    def cluster_documents(self, request: ClusterRequest) -> ClusterResponse:
        """Grupuje dokumenty odciskiem dokładnym i podobieństwem wektorowym."""
        documents = request.documents
        if not documents:
            return ClusterResponse(
                clusters=[],
                reduction_rate=0.0,
                total_processed=0,
                exact_duplicates_removed=0,
                method="pusty wsad",
            )
        if len(documents) > MAX_DOCUMENTS:
            raise InvalidDocumentBatchError(
                f"Wsad {len(documents)} dokumentów przekracza limit {MAX_DOCUMENTS}. "
                "Podziel go po stronie wywołującego — serwis nie próbkuje po cichu, bo "
                "zafałszowałoby to reduction_rate.",
                details={"received": len(documents), "limit": MAX_DOCUMENTS},
            )

        buckets = self._group_by_fingerprint(documents)

        vectors = self._resolve_vectors([members[0] for members in buckets])
        components = self._agglomerate(vectors, request.threshold)

        clusters = [self._build_cluster(component, buckets, vectors) for component in components]
        clusters.sort(key=lambda group: (-len(group.member_document_ids), group.cluster_id))

        total = len(documents)
        reduction = (total - len(clusters)) / total

        return ClusterResponse(
            clusters=clusters,
            reduction_rate=round(reduction, 2),
            total_processed=total,
            exact_duplicates_removed=total - len(buckets),
            method=(
                "odcisk SHA-256 tekstu bez interpunkcji i wielkości liter → aglomeracja o "
                f"średnim wiązaniu na kosinusie, próg {request.threshold}"
            ),
        )

    @staticmethod
    def _group_by_fingerprint(documents: list[DocumentItem]) -> list[list[DocumentItem]]:
        """Skleja dokumenty o identycznym znormalizowanym tekście.

        Grupy i ich zawartość są uporządkowane deterministycznie, żeby dalsze kroki dostały
        wejście niezależne od kolejności w żądaniu.
        """
        by_fingerprint: dict[str, list[DocumentItem]] = {}
        for document in documents:
            by_fingerprint.setdefault(content_fingerprint(document.content), []).append(document)

        # Reprezentantem grupy zostaje dokument niosący gotowy wektor, jeśli taki jest —
        # pozwala pominąć inferencję. Przy remisie decyduje najmniejszy identyfikator.
        groups = [
            sorted(members, key=lambda doc: (doc.embedding is None, doc.id))
            for members in by_fingerprint.values()
        ]
        groups.sort(key=lambda members: members[0].id)
        return groups

    def _resolve_vectors(self, representatives: list[DocumentItem]) -> NDArray[np.float64]:
        """Zwraca znormalizowane wektory reprezentantów, licząc tylko te nieprzekazane.

        Backend trzyma embeddingi w pgvector; ponowna inferencja dla dokumentu, który już je
        ma, jest czystym kosztem. Pole `DocumentItem.embedding` było do tej pory ignorowane.
        """
        dimension = self._embedder.dimension
        vectors: list[list[float] | None] = []
        missing_indices: list[int] = []

        for index, document in enumerate(representatives):
            if document.embedding is None:
                vectors.append(None)
                missing_indices.append(index)
                continue
            if len(document.embedding) != dimension:
                raise InvalidDocumentBatchError(
                    f"Dokument {document.id} niesie wektor o wymiarze "
                    f"{len(document.embedding)}, a aktywny model ma {dimension}.",
                    details={
                        "document_id": document.id,
                        "received_dimension": len(document.embedding),
                        "expected_dimension": dimension,
                    },
                )
            vectors.append(document.embedding)

        if missing_indices:
            computed = self._embedder.embed_texts(
                [representatives[index].content for index in missing_indices], normalize=True
            )
            for index, vector in zip(missing_indices, computed, strict=True):
                vectors[index] = vector

        matrix = np.asarray(vectors, dtype=np.float64)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        if bool(np.any(norms < _MIN_VECTOR_NORM)):
            offending = representatives[int(np.argmin(norms))].id
            raise InvalidDocumentBatchError(
                f"Dokument {offending} ma wektor zerowy — podobieństwo kosinusowe jest dla "
                "niego nieokreślone.",
                details={"document_id": offending},
            )
        return matrix / norms

    @staticmethod
    def _agglomerate(vectors: NDArray[np.float64], threshold: float) -> list[list[int]]:
        """Aglomeracja o średnim wiązaniu: w każdym kroku łączy globalnie najpodobniejszą parę.

        Średnie wiązanie liczone jest dokładnie, bez przechodzenia po parach. Dla wektorów
        znormalizowanych podobieństwo to iloczyn skalarny, więc średnia po parach klastrów A i
        B równa się (ΣA · ΣB) / (|A| · |B|) — wystarczy trzymać sumy i liczności.

        Zwraca listy indeksów wejściowych. Podział wynika z macierzy podobieństw, a nie z
        kolejności wejścia, co odróżnia tę metodę od zachłannego przypisania do pierwszego
        dokumentu, które było tu wcześniej.
        """
        count = vectors.shape[0]
        members: list[list[int]] = [[index] for index in range(count)]
        if count == 1:
            return members

        sums = vectors.copy()
        sizes = np.ones(count, dtype=np.float64)
        alive = np.ones(count, dtype=bool)

        similarities = (sums @ sums.T) / np.outer(sizes, sizes)
        np.fill_diagonal(similarities, -np.inf)

        for _ in range(count - 1):
            flat_index = int(np.argmax(similarities))
            left, right = divmod(flat_index, count)
            if similarities[left, right] < threshold:
                break

            target, absorbed = (left, right) if left < right else (right, left)
            sums[target] += sums[absorbed]
            sizes[target] += sizes[absorbed]
            members[target].extend(members[absorbed])
            members[absorbed] = []
            alive[absorbed] = False

            updated = (sums @ sums[target]) / (sizes * sizes[target])
            updated[~alive] = -np.inf
            updated[target] = -np.inf
            similarities[target, :] = updated
            similarities[:, target] = updated
            similarities[absorbed, :] = -np.inf
            similarities[:, absorbed] = -np.inf

        return [sorted(members[index]) for index in range(count) if alive[index]]

    @staticmethod
    def _build_cluster(
        component: list[int],
        buckets: list[list[DocumentItem]],
        vectors: NDArray[np.float64],
    ) -> ClusterGroup:
        """Składa klaster: centroid, reprezentanta najbliższego centroidowi i spójność.

        `cohesion_score` to średni kosinus członków do centroidu klastra — miara tego, jak
        ciasny jest klaster. Poprzednia wersja uśredniała podobieństwa do pierwszego
        napotkanego dokumentu i zawsze doliczała do średniej sztuczną jedynkę.
        """
        member_vectors = vectors[component]
        centroid = member_vectors.mean(axis=0)
        centroid_norm = float(np.linalg.norm(centroid))

        if centroid_norm < _MIN_VECTOR_NORM:
            # Wektory znoszą się wzajemnie — klaster nie ma sensownego środka. Zwracamy
            # zerową spójność zamiast liczby udającej pomiar.
            cohesion = 0.0
            representative_position = 0
        else:
            member_similarities = member_vectors @ (centroid / centroid_norm)
            cohesion = float(member_similarities.mean())
            representative_position = int(np.argmax(member_similarities))

        member_ids = sorted(document.id for index in component for document in buckets[index])
        representative = buckets[component[representative_position]][0]
        # Identyfikator wyprowadzony ze składu klastra, a nie z reprezentanta: ten sam zestaw
        # dokumentów daje ten sam `cluster_id` między wywołaniami, więc kaskada może po nim
        # cache'ować wynik streszczenia.
        digest = hashlib.blake2b("\x00".join(member_ids).encode("utf-8"), digest_size=6).hexdigest()

        return ClusterGroup(
            cluster_id=f"cls_{digest}",
            representative_document_id=representative.id,
            member_document_ids=member_ids,
            cohesion_score=round(cohesion, 3),
        )
