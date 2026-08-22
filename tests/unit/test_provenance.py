"""Unit tests for strict provenance validation."""

import pytest
from pydantic import ValidationError

from barometr_ai.domain.provenance import GroundedStatement, ProvenanceSpan
from barometr_ai.services.provenance_service import ProvenanceService


def test_provenance_span_validation_success():
    source_text = "Ustawa z dnia 7 lipca 2023 r. o zmianie ustawy o planowaniu przestrzennym."
    span = ProvenanceSpan(
        source_document_id="doc_123",
        char_start=0,
        char_end=29,
        exact_quote="Ustawa z dnia 7 lipca 2023 r.",
    )
    assert span.validate_against_text(source_text) is True


def test_provenance_span_validation_mismatch():
    source_text = "Ustawa o podatkach."
    span = ProvenanceSpan(
        source_document_id="doc_123",
        char_start=0,
        char_end=10,
        exact_quote="Niepoprawny",
    )
    assert span.validate_against_text(source_text) is False


def test_grounded_statement_requires_provenance():
    with pytest.raises(ValidationError):
        GroundedStatement(text="Fakt bez zrodla", provenance=[])


def test_provenance_service_filters_ungrounded():
    source_text = "Dokument źródłowy z faktami."
    valid_span = ProvenanceSpan(
        source_document_id="doc_1",
        char_start=0,
        char_end=17,
        exact_quote="Dokument źródłowy",
    )
    invalid_span = ProvenanceSpan(
        source_document_id="doc_1",
        char_start=0,
        char_end=17,
        exact_quote="Błędny cytat",
    )

    valid_stmt = GroundedStatement(text="Zweryfikowane", provenance=[valid_span])
    invalid_stmt = GroundedStatement(text="Niezgodne", provenance=[invalid_span])

    filtered = ProvenanceService.filter_ungrounded([valid_stmt, invalid_stmt], source_text)
    assert len(filtered) == 1
    assert filtered[0].text == "Zweryfikowane"