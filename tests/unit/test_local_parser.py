"""Testy parsera dokumentów BIP — rozpoznawanie kwot i przedmiotu uchwały.

Każdy test odpowiada konkretnej pomyłce wskazanej w audycie: separatory tysięcy zaniżające
kwotę o trzy rzędy wielkości oraz branie pierwszej kwoty w dokumencie jako kwoty uchwały.
"""

import pytest

from barometr_ai.domain.enterprise_models import LocalDocType, LocalParseRequest
from barometr_ai.services.local_parser_service import LocalDocumentParserService


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10.000", 10_000.0),  # regresja: dawniej 10.0 — kropka jako separator tysięcy
        ("15 000 000", 15_000_000.0),
        ("1 234,56", 1_234.56),
        ("1.234.567,89", 1_234_567.89),
        ("15000000", 15_000_000.0),
        ("10.50", 10.50),  # kropka + dokładnie dwie cyfry na końcu = separator dziesiętny
    ],
)
def test_polish_amount_formats(raw: str, expected: float) -> None:
    assert LocalDocumentParserService._parse_polish_amount(raw) == expected


def _parse(text: str):
    return LocalDocumentParserService.parse_document(
        LocalParseRequest(bip_text=text, gmina_teryt="020101")
    )


def test_budget_amount_requires_budget_context() -> None:
    """Kwota bez kontekstu budżetowego nie może zostać podana jako wpływ budżetowy.

    Regresja: poprzednia wersja brała pierwszą kwotę w dokumencie, więc opłata skarbowa
    wymieniona w preambule trafiała do `budget_impact_pln`.
    """
    result = _parse(
        "Uchwała Nr V/11/2026 w sprawie nadania nazwy ulicy. "
        "Opłata skarbowa wynosi 17 zł zgodnie z ustawą o opłacie skarbowej."
    )
    assert result.budget_impact_pln is None
    assert result.detected_amounts_pln == [17.0]


def test_budget_amount_detected_in_budget_context() -> None:
    result = _parse(
        "Uchwała Nr V/12/2026 w sprawie budżetu gminy. Dochody wynoszą 15 000 000,50 zł."
    )
    assert result.doc_type is LocalDocType.BUDGET_UCHWALA
    assert result.budget_impact_pln == 15_000_000.50


def test_subject_extracted_from_standard_phrase() -> None:
    """Przedmiot pochodzi z formuły 'w sprawie ...', a nie ze sklejenia kodu TERYT."""
    result = _parse(
        "Uchwała Nr XIV/120/2026 w sprawie zmiany miejscowego planu zagospodarowania "
        "przestrzennego. Rada gminy uchwala co następuje."
    )
    assert result.subject == "zmiany miejscowego planu zagospodarowania przestrzennego"
    assert result.is_spatial_planning is True


def test_summary_is_not_fabricated() -> None:
    """Streszczenie prostym językiem wymaga modelu — szablon f-string nim nie był."""
    result = _parse("Protokół z sesji Rady Gminy odbytej w dniu 12 marca 2026 roku.")
    assert result.summary_plain_polish is None
    assert result.doc_type is LocalDocType.PROTOKOL_SESJI
