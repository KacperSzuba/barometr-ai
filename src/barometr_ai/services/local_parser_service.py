"""Parser uchwał, protokołów, budżetów i MPZP samorządowych (F4 Local)."""

import re

from barometr_ai.domain.enterprise_models import (
    LocalDocType,
    LocalParseRequest,
    LocalParseResponse,
)

_RESOLUTION_NUMBER = re.compile(
    r"(Uchwał[ay]\s+Nr\s+[IVXLC0-9]+\s*/\s*[0-9]+\s*/\s*[0-9]{2,4})", re.IGNORECASE
)
_SUBJECT = re.compile(r"w\s+sprawie\s+([^.\n]{5,200})", re.IGNORECASE)
_AMOUNT = re.compile(r"(\d[\d\s\u00a0.,]*\d|\d)\s*(?:zł|złotych|PLN)", re.IGNORECASE)

#: Słowa, które muszą stać blisko kwoty, żeby uznać ją za kwotę budżetową uchwały.
#: Wyłącznie terminy budżetowe — ogólne czasowniki kwotowe ("wynosi", "kwota", "ustala się")
#: pojawiają się przy każdej sumie w dokumencie i wciągałyby np. opłatę skarbową.
_BUDGET_CONTEXT = (
    "budżet",
    "budzet",
    "dochod",
    "wydatk",
    "deficyt",
    "nadwyżk",
    "plan finansowy",
)
_CONTEXT_WINDOW = 120

#: Rdzenie rozpoznające typ dokumentu, odporne na odmianę przez przypadki. Kolejność ma
#: znaczenie — uchwała budżetowa też bywa "uchwałą rady", więc bardziej szczegółowe idą pierwsze.
_TYPE_MARKERS: tuple[tuple[LocalDocType, tuple[str, ...]], ...] = (
    (
        LocalDocType.MPZP,
        (
            "zagospodarowania przestrzenn",
            "planu miejscowego",
            "planie miejscowym",
            "plan miejscowy",
            "mpzp",
            "studium uwarunkowa",
        ),
    ),
    (
        LocalDocType.BUDGET_UCHWALA,
        ("budżet", "budzet", "dochodach i wydatkach", "wieloletniej prognozy finansowej"),
    ),
    (
        LocalDocType.PROTOKOL_SESJI,
        ("protokół", "protokol", "sesji rady", "sesja rady"),
    ),
)


class LocalDocumentParserService:
    """Przetwarza niestandardowe dokumenty BIP samorządu terytorialnego (gminy i powiaty)."""

    @staticmethod
    def parse_document(request: LocalParseRequest) -> LocalParseResponse:
        text = request.bip_text
        lowered = text.lower()

        doc_type = LocalDocumentParserService._detect_type(lowered)
        is_spatial = doc_type is LocalDocType.MPZP

        number_match = _RESOLUTION_NUMBER.search(text)
        subject_match = _SUBJECT.search(text)
        amounts = LocalDocumentParserService._extract_amounts(text)
        budget_impact = LocalDocumentParserService._budget_amount(text, amounts)

        return LocalParseResponse(
            doc_type=doc_type,
            resolution_number=number_match.group(1) if number_match else None,
            # Przedmiot uchwały wyciągany z formuły "w sprawie ...", a nie sklejany z TERYT.
            subject=subject_match.group(1).strip() if subject_match else None,
            is_spatial_planning=is_spatial,
            budget_impact_pln=budget_impact,
            detected_amounts_pln=[amount for _, amount in amounts],
            # Streszczenie prostym językiem wymaga modelu. Poprzednia wersja zwracała
            # szablon f-string, który nie opisywał treści dokumentu.
            summary_plain_polish=None,
        )

    @staticmethod
    def _detect_type(lowered: str) -> LocalDocType:
        """Rozpoznaje typ dokumentu po rdzeniach odpornych na odmianę.

        Dopasowanie do pełnych form mianownikowych gubiło typowe zapisy z uchwał —
        "zmiany miejscowego planu zagospodarowania przestrzennego" nie pasowało do wzorca
        "plan zagospodarowania".
        """
        for doc_type, markers in _TYPE_MARKERS:
            if any(marker in lowered for marker in markers):
                return doc_type
        return LocalDocType.UCHWALA_RADY

    @staticmethod
    def _extract_amounts(text: str) -> list[tuple[int, float]]:
        """Zwraca pary (pozycja, kwota) dla wszystkich kwot znalezionych w tekście."""
        found: list[tuple[int, float]] = []
        for match in _AMOUNT.finditer(text):
            value = LocalDocumentParserService._parse_polish_amount(match.group(1))
            if value is not None:
                found.append((match.start(), value))
        return found

    @staticmethod
    def _parse_polish_amount(raw: str) -> float | None:
        """Interpretuje zapis kwoty zgodnie z konwencją polską.

        Przecinek to separator dziesiętny; spacje i kropki to separatory tysięcy. Wyjątkiem
        jest kropka poprzedzająca dokładnie dwie cyfry na końcu przy braku innych kropek —
        wtedy traktujemy ją jako dziesiętną. Poprzednia wersja zamieniała każdy przecinek
        na kropkę i usuwała spacje, przez co "10.000 zł" dawało 10.0.
        """
        cleaned = raw.replace("\u00a0", "").replace(" ", "")
        if not cleaned:
            return None

        if "," in cleaned:
            integer_part, _, fraction = cleaned.rpartition(",")
            candidate = f"{integer_part.replace('.', '')}.{fraction}"
        elif cleaned.count(".") == 1 and len(cleaned.rsplit(".", 1)[1]) == 2:
            candidate = cleaned
        else:
            candidate = cleaned.replace(".", "")

        try:
            return float(candidate)
        except ValueError:
            return None

    @staticmethod
    def _budget_amount(text: str, amounts: list[tuple[int, float]]) -> float | None:
        """Zwraca kwotę tylko wtedy, gdy stoi w kontekście budżetowym.

        Poprzednia wersja brała pierwszą kwotę w dokumencie i podawała ją jako wpływ
        budżetowy — także gdy była to na przykład opłata skarbowa wymieniona w preambule.
        """
        lowered = text.lower()
        for position, value in amounts:
            window = lowered[max(0, position - _CONTEXT_WINDOW) : position]
            if any(marker in window for marker in _BUDGET_CONTEXT):
                return value
        return None
