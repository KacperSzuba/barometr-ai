"""Testy bramki proweniencji: parser sekcji, wykrywanie rozjechanych offsetów, regeneracja.

Te testy sprawdzają, czy wynik jest poprawny — nie czy kod się wykonuje. Każdy z nich
odpowiada konkretnej klasie awarii wskazanej w audycie.
"""

import pytest

from barometr_ai.core.config import Settings
from barometr_ai.domain.llm import (
    CitedSegment,
    CitedSpan,
    LLMCompletion,
    LLMPrompt,
    SummarySection,
)
from barometr_ai.domain.models import SummarizeRequest
from barometr_ai.services.cost_tracker_service import CostTrackerService
from barometr_ai.services.provenance_service import ProvenanceService
from barometr_ai.services.section_parser import markers_seen, parse_sections
from barometr_ai.services.summarizer_service import SummarizerService

DOCUMENT = (
    "Nowelizacja ustawy o odnawialnych zrodlach energii wprowadza uproszczona procedure "
    "przylaczenia mikroinstalacji. Przepisy dotycza przedsiebiorcow eksploatujacych "
    "instalacje fotowoltaiczne o mocy do 50 kW. Ustawa wchodzi w zycie po uplywie 30 dni "
    "od dnia ogloszenia."
)


class ScriptedLLM:
    """Adapter testowy odtwarzający zadaną sekwencję odpowiedzi modelu."""

    def __init__(self, responses: list[list[CitedSegment]]) -> None:
        self._responses = responses
        self.prompts: list[LLMPrompt] = []

    model_name = "scripted"
    model_version = "scripted@v1"
    is_generative = True

    async def complete(self, prompt: LLMPrompt) -> LLMCompletion:
        self.prompts.append(prompt)
        index = min(len(self.prompts) - 1, len(self._responses) - 1)
        return LLMCompletion(
            segments=self._responses[index],
            model_name=self.model_name,
            model_version=self.model_version,
            prompt_tokens=100,
            completion_tokens=20,
        )


def _cited(text: str, quote: str) -> CitedSegment:
    """Buduje segment z odwołaniem do faktycznego fragmentu dokumentu.

    Offsety liczone są z dokumentu, a nie wpisywane ręcznie — inaczej test sprawdzałby
    zgodność ze swoją własną pomyłką zamiast z zachowaniem walidatora.
    """
    start = DOCUMENT.index(quote)
    return CitedSegment(
        text=text,
        citations=[CitedSpan(char_start=start, char_end=start + len(quote), cited_text=quote)],
    )


def _marker(name: str) -> CitedSegment:
    return CitedSegment(text=f"[{name}]\n")


def _full_answer() -> list[CitedSegment]:
    return [
        _marker("CO_SIE_ZMIENIA"),
        _cited("Wprowadza uproszczona procedure przylaczenia.", "wprowadza uproszczona procedure"),
        _marker("KOGO_DOTYCZY"),
        _cited("Dotyczy przedsiebiorcow z instalacjami PV.", "Przepisy dotycza przedsiebiorcow"),
        _marker("CO_DALEJ"),
        _cited(
            "Wejscie w zycie po 30 dniach od ogloszenia.",
            "Ustawa wchodzi w zycie po uplywie 30 dni",
        ),
        _marker("USTALENIA_DODATKOWE"),
        CitedSegment(text="BRAK_PODSTAWY\n"),
    ]


def _service(llm: ScriptedLLM, settings: Settings) -> SummarizerService:
    return SummarizerService(
        llm=llm, cost_tracker=CostTrackerService(daily_budget=10_000_000), settings=settings
    )


def _request() -> SummarizeRequest:
    return SummarizeRequest(document_id="druk_140", content=DOCUMENT, max_sentences=4)


# --- walidator odwołań ---


def test_citation_with_drifted_offsets_is_rejected() -> None:
    """Odwołanie, którego treść nie zgadza się z wycinkiem źródła, nie może przejść."""
    drifted = CitedSpan(char_start=0, char_end=20, cited_text="tresc ktorej tam nie ma")
    assert (
        ProvenanceService.to_provenance_span(drifted, document_id="d1", source_text=DOCUMENT)
        is None
    )


def test_citation_out_of_document_bounds_is_rejected() -> None:
    out_of_range = CitedSpan(char_start=10, char_end=len(DOCUMENT) + 50, cited_text="")
    assert (
        ProvenanceService.to_provenance_span(out_of_range, document_id="d1", source_text=DOCUMENT)
        is None
    )


def test_valid_citation_keeps_exact_source_slice() -> None:
    """`exact_quote` musi być wycinkiem źródła znak w znak — także z białymi znakami."""
    span = ProvenanceService.to_provenance_span(
        CitedSpan(char_start=0, char_end=30, cited_text=DOCUMENT[0:30]),
        document_id="d1",
        source_text=DOCUMENT,
    )
    assert span is not None
    assert span.exact_quote == DOCUMENT[0:30]
    assert span.validate_against_text(DOCUMENT) is True


def test_provenance_span_does_not_strip_whitespace() -> None:
    """Regresja: przycinanie cytatu rozjeżdżało go z offsetami i odrzucało poprawne odwołania."""
    text = "  fragment z bialymi znakami  "
    span = ProvenanceService.to_provenance_span(
        CitedSpan(char_start=0, char_end=len(text), cited_text=text),
        document_id="d1",
        source_text=text,
    )
    assert span is not None
    assert span.exact_quote == text


# --- parser sekcji ---


def test_parser_splits_sections_and_drops_no_basis() -> None:
    sections = parse_sections(_full_answer())
    assert len(sections[SummarySection.WHAT_CHANGED]) == 1
    assert len(sections[SummarySection.WHO_IS_AFFECTED]) == 1
    assert len(sections[SummarySection.NEXT_STEPS]) == 1
    assert sections[SummarySection.ADDITIONAL_FINDINGS] == []


def test_parser_ignores_preamble_before_first_marker() -> None:
    """Treść przed pierwszym znacznikiem nie należy do żadnej sekcji i musi zniknąć."""
    segments = [CitedSegment(text="Oto streszczenie:\n"), *_full_answer()]
    sections = parse_sections(segments)
    assert all("Oto streszczenie" not in s.text for s in sections[SummarySection.WHAT_CHANGED])


def test_parser_handles_marker_inline_with_content() -> None:
    """Model bywa zwraca znacznik i treść w jednym bloku — offsety muszą przetrwać podział."""
    segments = [
        CitedSegment(
            text="[CO_SIE_ZMIENIA]\nUproszczona procedura.",
            citations=[CitedSpan(char_start=0, char_end=30, cited_text=DOCUMENT[0:30])],
        )
    ]
    sections = parse_sections(segments)
    assert len(sections[SummarySection.WHAT_CHANGED]) == 1
    assert sections[SummarySection.WHAT_CHANGED][0].citations[0].char_start == 0


# --- orkiestracja i regeneracja ---


async def test_summary_without_citations_is_rejected_not_returned(settings: Settings) -> None:
    """Zdanie bez odwołania nie może trafić do odpowiedzi — punkt 4 zadania F1."""
    uncited = [
        _marker("CO_SIE_ZMIENIA"),
        CitedSegment(text="Ustawa radykalnie zmienia rynek energii."),
        _marker("KOGO_DOTYCZY"),
        CitedSegment(text="BRAK_PODSTAWY\n"),
        _marker("CO_DALEJ"),
        CitedSegment(text="BRAK_PODSTAWY\n"),
        _marker("USTALENIA_DODATKOWE"),
        CitedSegment(text="BRAK_PODSTAWY\n"),
    ]
    service = _service(ScriptedLLM([uncited]), settings)
    response = await service.summarize(_request())

    assert response.what_changed is None
    assert response.summary_bullets == []
    assert "co się zmienia" in response.rejected_sections


async def test_rejected_section_is_regenerated_and_accepted(settings: Settings) -> None:
    """Pętla korekty: pierwsza próba bez odwołania, druga poprawna."""
    bad = [
        _marker("CO_SIE_ZMIENIA"),
        CitedSegment(text="Twierdzenie bez zrodla."),
        _marker("KOGO_DOTYCZY"),
        _cited("Dotyczy przedsiebiorcow.", "Przepisy dotycza przedsiebiorcow"),
        _marker("CO_DALEJ"),
        CitedSegment(text="BRAK_PODSTAWY\n"),
        _marker("USTALENIA_DODATKOWE"),
        CitedSegment(text="BRAK_PODSTAWY\n"),
    ]
    llm = ScriptedLLM([bad, _full_answer()])
    response = await _service(llm, settings).summarize(_request())

    assert response.attempts == 2
    assert response.rejected_sections == []
    assert response.what_changed is not None
    # Druga próba niesie blok korekty wskazujący odrzuconą sekcję.
    assert "KOREKTA PO ODRZUCENIU" in llm.prompts[1].user
    assert "co się zmienia" in llm.prompts[1].user


async def test_accepted_sections_are_not_regenerated(settings: Settings) -> None:
    """Sekcja raz przyjęta nie może zostać nadpisana treścią z próby korekty."""
    llm = ScriptedLLM(
        [
            [
                _marker("CO_SIE_ZMIENIA"),
                CitedSegment(text="Bez zrodla."),
                _marker("KOGO_DOTYCZY"),
                _cited("Dotyczy przedsiebiorcow.", "Przepisy dotycza przedsiebiorcow"),
                _marker("CO_DALEJ"),
                CitedSegment(text="BRAK_PODSTAWY\n"),
                _marker("USTALENIA_DODATKOWE"),
                CitedSegment(text="BRAK_PODSTAWY\n"),
            ],
            _full_answer(),
        ]
    )
    response = await _service(llm, settings).summarize(_request())
    assert response.who_is_affected is not None
    assert response.who_is_affected.text == "Dotyczy przedsiebiorcow."


async def test_declared_no_basis_does_not_trigger_regeneration(settings: Settings) -> None:
    """BRAK_PODSTAWY to poprawna odpowiedź, nie awaria — nie wolno jej ponawiać."""
    llm = ScriptedLLM([_full_answer()])
    response = await _service(llm, settings).summarize(_request())

    assert response.attempts == 1
    assert len(llm.prompts) == 1
    assert response.additional_findings == []
    assert response.rejected_sections == []


async def test_metadata_reports_real_model_and_usage(settings: Settings) -> None:
    """Metadane odpowiedzi muszą opisywać to, co faktycznie wykonało inferencję."""
    llm = ScriptedLLM([_full_answer()])
    response = await _service(llm, settings).summarize(_request())

    assert response.model_version == "scripted@v1"
    assert response.prompt_version.startswith("summary_executive_pl@")
    assert response.is_generative is True
    assert response.tokens_are_estimated is False
    assert response.total_tokens == 120


async def test_heuristic_adapter_is_flagged_as_non_generative(
    summarizer: SummarizerService,
) -> None:
    """Wynik adaptera zastępczego nigdy nie może udawać wyniku modelu językowego."""
    response = await summarizer.summarize(_request())

    assert response.is_generative is False
    assert response.tokens_are_estimated is True
    assert response.model_version == "heuristic-v0"
    # Mimo to każde zwrócone twierdzenie musi mieć poprawną proweniencję.
    for statement in response.summary_bullets:
        for span in statement.provenance:
            assert DOCUMENT[span.char_start : span.char_end] == span.exact_quote


async def test_budget_gate_blocks_before_calling_provider(settings: Settings) -> None:
    """Bramka budżetowa musi zadziałać przed wywołaniem, a nie po wydaniu tokenów."""
    from barometr_ai.core.exceptions import BudgetExceededError

    llm = ScriptedLLM([_full_answer()])
    service = SummarizerService(
        llm=llm, cost_tracker=CostTrackerService(daily_budget=10), settings=settings
    )
    with pytest.raises(BudgetExceededError):
        await service.summarize(_request())
    assert llm.prompts == []


# --- awaria formatu odpowiedzi ---


def test_parser_rozroznia_brak_znacznika_od_braku_podstawy() -> None:
    """Sekcja pusta wygląda tak samo w obu przypadkach — rozstrzyga obecność znacznika."""
    with_marker = [CitedSegment(text="[CO_SIE_ZMIENIA]\nBRAK_PODSTAWY")]
    assert parse_sections(with_marker)[SummarySection.WHAT_CHANGED] == []
    assert SummarySection.WHAT_CHANGED in markers_seen(with_marker)

    without_marker = [CitedSegment(text="Jakas tresc bez zadnego znacznika.")]
    assert parse_sections(without_marker)[SummarySection.WHAT_CHANGED] == []
    assert markers_seen(without_marker) == set()


async def test_odpowiedz_bez_znacznikow_nie_udaje_pustego_streszczenia(
    settings: Settings,
) -> None:
    """Regresja: model gubiący znaczniki dawał HTTP 200 z zerem twierdzeń i zerem odrzuceń.

    Sekcja bez znacznika była nieodróżnialna od sekcji, w której model świadomie wpisał
    BRAK_PODSTAWY, więc awaria formatu przechodziła jako poprawna odpowiedź — bez
    regeneracji i bez jakiegokolwiek śladu w wyniku.
    """
    llm = ScriptedLLM([[CitedSegment(text="Tresc odpowiedzi bez zadnego znacznika sekcji.")]])
    service = SummarizerService(
        llm=llm, cost_tracker=CostTrackerService(daily_budget=1_000_000), settings=settings
    )

    response = await service.summarize(
        SummarizeRequest(document_id="doc_bez_znacznikow", content=DOCUMENT)
    )

    # Awaria formatu uruchamia regenerację, a nie ciche przyjęcie pustki.
    assert len(llm.prompts) > 1
    assert response.summary_bullets == []
    # Po wyczerpaniu prób każda sekcja jest raportowana jako odrzucona.
    assert len(response.rejected_sections) == len(SummarySection)


async def test_sekcja_z_brak_podstawy_nie_jest_odrzucana(settings: Settings) -> None:
    """Świadoma deklaracja braku podstawy to poprawna odpowiedź — bez regeneracji."""
    answer = [
        CitedSegment(text="[CO_SIE_ZMIENIA]\n"),
        _cited("Uproszczona procedura przylaczenia.", "uproszczona procedure"),
        CitedSegment(text="\n[KOGO_DOTYCZY]\nBRAK_PODSTAWY\n[CO_DALEJ]\nBRAK_PODSTAWY\n"),
        CitedSegment(text="[USTALENIA_DODATKOWE]\nBRAK_PODSTAWY"),
    ]
    llm = ScriptedLLM([answer])
    service = SummarizerService(
        llm=llm, cost_tracker=CostTrackerService(daily_budget=1_000_000), settings=settings
    )

    response = await service.summarize(
        SummarizeRequest(document_id="doc_brak_podstawy", content=DOCUMENT)
    )

    assert len(llm.prompts) == 1  # brak regeneracji
    assert response.rejected_sections == []
    assert response.what_changed is not None
    assert response.who_is_affected is None


async def test_zuzycie_tokenow_trafia_do_metryki_per_klient(
    settings: Settings, monkeypatch
) -> None:
    """Regresja: `record_tokens` istniało, ale nikt go nie wołał — metryka nigdy nie powstawała.

    Licznik budżetu i metryka to dwie różne rzeczy: pierwsza zeruje się o północy i pilnuje
    limitu, druga jest szeregiem czasowym rozliczenia. Dotąd działała tylko pierwsza.
    """
    recorded: list[dict[str, object]] = []

    monkeypatch.setattr(
        "barometr_ai.services.summarizer_service.record_tokens",
        lambda **kwargs: recorded.append(kwargs),
    )

    llm = ScriptedLLM([_full_answer()])
    service = SummarizerService(
        llm=llm, cost_tracker=CostTrackerService(daily_budget=1_000_000), settings=settings
    )

    await service.summarize(
        SummarizeRequest(document_id="doc_metryka", content=DOCUMENT), client_id="klient_7"
    )

    assert len(recorded) == 1
    assert recorded[0]["client_id"] == "klient_7"
    assert recorded[0]["tokens"] == 120  # prompt_tokens + completion_tokens ze ScriptedLLM
    # Metryka opisuje model, który faktycznie wykonał inferencję (AGENTS.md §4).
    assert recorded[0]["model_version"] == llm.model_version
