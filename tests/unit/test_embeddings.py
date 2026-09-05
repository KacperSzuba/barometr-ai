"""Testy jakościowe dla lokalnego modelu embeddingów i podobieństwa kosinusowego."""

import pytest

#: Cały moduł mierzy zachowanie realnego adaptera ONNX.
pytestmark = pytest.mark.model

import numpy as np

from barometr_ai.adapters.fastembed_adapter import FastEmbedAdapter


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Oblicza cosinus kąta między dwoma wektorami (wartość od -1.0 do 1.0)."""
    a = np.array(vec_a)
    b = np.array(vec_b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def test_embedder_dimension_and_count(embedder: FastEmbedAdapter) -> None:
    texts = ["Pierwszy tekst prawny", "Drugi tekst prawny"]
    vectors = embedder.embed_texts(texts)

    assert len(vectors) == 2
    assert len(vectors[0]) == embedder.dimension
    assert embedder.dimension == 384


def test_semantic_similarity_polish_legal_texts(embedder: FastEmbedAdapter) -> None:
    """Weryfikacja, czy model rozumie semantykę polskich pojęć podatkowych vs przyrodniczych."""
    doc_tax_1 = "Projekt ustawy o zmianie stawek podatku dochodowego od osób fizycznych."
    doc_tax_2 = "Nowelizacja przepisów w zakresie podatków PIT i ulg dla przedsiębiorców."
    doc_nature = "Plan ochrony populacji żubra i zalesiania terenów parków narodowych."

    vectors = embedder.embed_texts([doc_tax_1, doc_tax_2, doc_nature])
    vec_tax1, vec_tax2, vec_nature = vectors[0], vectors[1], vectors[2]

    similarity_taxes = cosine_similarity(vec_tax1, vec_tax2)
    similarity_tax_vs_nature = cosine_similarity(vec_tax1, vec_nature)

    # Semantyczna asercja: podatki są semantycznie blisko PIT i bardzo daleko od ochrony przyrody
    assert similarity_taxes > 0.60
    assert similarity_tax_vs_nature < 0.30
    assert similarity_taxes > similarity_tax_vs_nature + 0.35
