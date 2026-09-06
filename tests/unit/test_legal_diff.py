"""Testy drzewiastego diffa aktów prawnych: parsowanie hierarchii i przenumerowanie."""

from barometr_ai.domain.advanced_models import LegalDiffRequest
from barometr_ai.services.legal_diff_service import LegalDiffService, parse_legal_units

#: Akt z pełną hierarchią: artykuł → ustęp → punkt → litera, z powrotem na poziom ustępu.
AKT = """Art. 1. Ustawa określa zasady wsparcia odbiorców energii.
Art. 2. 1. Wsparciem obejmuje się odbiorców końcowych.
2. Wsparcie przysługuje, jeżeli spełnione są łącznie warunki:
1) odbiorca jest gospodarstwem domowym;
2) zużycie nie przekracza progu, przy czym:
a) dla gospodarstw jednoosobowych próg wynosi 1500 kWh,
b) dla pozostałych gospodarstw próg wynosi 2000 kWh;
3) wniosek złożono w terminie.
3. Próg roczny wynosi 2000 kWh.
Art. 3. Ustawa wchodzi w życie po upływie 14 dni."""


def diff(version_a: str, version_b: str, comments: list[dict[str, str]] | None = None):
    return LegalDiffService.compare_and_correlate(
        LegalDiffRequest(
            version_a_text=version_a,
            version_b_text=version_b,
            consultation_comments=comments or [],
        )
    )


# --- Parsowanie hierarchii ---------------------------------------------------------------


def test_parser_schodzi_przez_wszystkie_poziomy() -> None:
    units = parse_legal_units(AKT)

    assert "Art. 2 ust. 2 pkt 2 lit. a" in units
    assert (
        units["Art. 2 ust. 2 pkt 2 lit. a"].text
        == "dla gospodarstw jednoosobowych próg wynosi 1500 kWh,"
    )
    assert units["Art. 2 ust. 2 pkt 1"].text == "odbiorca jest gospodarstwem domowym;"


def test_parser_wraca_na_wyzszy_poziom_po_zagniezdzeniu() -> None:
    """Po literach `a)` i `b)` wiersz `3.` musi wrócić na poziom ustępu artykułu,
    a nie zostać kolejną literą albo punktem."""
    units = parse_legal_units(AKT)

    assert "Art. 2 ust. 3" in units
    assert units["Art. 2 ust. 3"].text == "Próg roczny wynosi 2000 kWh."
    assert "Art. 2 ust. 2 pkt 2 lit. b" in units


def test_parser_nie_myli_ustepu_z_punktem() -> None:
    """`1.` to ustęp, `1)` to punkt — rozróżnia je znak zamykający, nie kolejność."""
    units = parse_legal_units(AKT)

    assert "Art. 2 ust. 1" in units
    assert "Art. 2 ust. 2 pkt 1" in units
    assert "Art. 2 pkt 1" not in units


def test_parser_obsluguje_paragrafy_rozporzadzen() -> None:
    units = parse_legal_units(
        "§ 1. Rozporządzenie określa tryb.\n§ 2. 1. Wniosek składa się pisemnie."
    )

    assert units["§ 1"].text == "Rozporządzenie określa tryb."
    assert units["§ 2 ust. 1"].text == "Wniosek składa się pisemnie."


def test_parser_numeruje_tiret_w_obrebie_rodzica() -> None:
    """Tiret nie mają numeracji w tekście — bez nadania jej nie da się ich zaadresować."""
    units = parse_legal_units(
        "Art. 1. 1. Wykaz obejmuje:\n1) dokumenty, w tym:\n– umowy,\n– faktury."
    )

    assert units["Art. 1 ust. 1 pkt 1 tiret 1"].text == "umowy,"
    assert units["Art. 1 ust. 1 pkt 1 tiret 2"].text == "faktury."


# --- Diff na poziomie jednostki ----------------------------------------------------------


def test_zmiana_w_literze_nie_zaraza_przodkow() -> None:
    """Sedno diffa drzewiastego: raportowana jest najgłębsza jednostka, która się zmieniła.
    Poprzednia wersja oznaczała cały artykuł jako MODIFIED i wiązała z nim wszystkie uwagi."""
    zmieniony = AKT.replace("próg wynosi 2000 kWh;", "próg wynosi 2500 kWh;")

    response = diff(AKT, zmieniony)

    assert len(response.changes) == 1
    assert response.changes[0].article_ref == "Art. 2 ust. 2 pkt 2 lit. b"
    assert response.changes[0].change_type == "MODIFIED"


def test_dodanie_litery_raportowane_punktowo() -> None:
    zmieniony = AKT.replace(
        "b) dla pozostałych gospodarstw próg wynosi 2000 kWh;",
        "b) dla pozostałych gospodarstw próg wynosi 2000 kWh,\nc) dla podmiotów wrażliwych próg nie obowiązuje;",
    )

    response = diff(AKT, zmieniony)

    dodane = [c for c in response.changes if c.change_type == "ADDED"]
    assert [c.article_ref for c in dodane] == ["Art. 2 ust. 2 pkt 2 lit. c"]


# --- Przenumerowanie ---------------------------------------------------------------------


def test_wstawienie_artykulu_daje_renumbered_a_nie_modified() -> None:
    """Wstawienie artykułu przesuwa kolejne. Bez wykrywania przenumerowania każdy z nich
    wyglądałby na zmieniony merytorycznie — i tak właśnie było wcześniej."""
    version_a = "Art. 1. Przepisy ogólne.\nArt. 2. Definicje ustawowe.\nArt. 3. Wejście w życie."
    version_b = (
        "Art. 1. Przepisy ogólne.\n"
        "Art. 2. Zakres podmiotowy ustawy.\n"
        "Art. 3. Definicje ustawowe.\n"
        "Art. 4. Wejście w życie."
    )

    response = diff(version_a, version_b)

    przeniesione = {
        (c.previous_ref, c.article_ref) for c in response.changes if c.change_type == "RENUMBERED"
    }
    assert przeniesione == {("Art. 2", "Art. 3"), ("Art. 3", "Art. 4")}
    # Merytorycznie zmienił się wyłącznie nowo wstawiony artykuł.
    assert response.significant_changes_count == 1
    dodane = [c for c in response.changes if c.change_type == "ADDED"]
    assert [c.article_ref for c in dodane] == ["Art. 2"]


def test_przenumerowanie_artykulu_nie_powiela_wpisow_dla_dzieci() -> None:
    """Przesunięcie artykułu przesuwa wszystkie jego ustępy. Raportujemy sam artykuł —
    ale dzieci muszą zostać rozliczone, inaczej wróciłyby jako fałszywe DELETED + ADDED."""
    version_a = "Art. 1. Przepis wprowadzający.\n1. Pierwszy ustęp.\n2. Drugi ustęp."
    version_b = (
        "Art. 1. Zupełnie nowy przepis.\n"
        "Art. 2. Przepis wprowadzający.\n"
        "1. Pierwszy ustęp.\n"
        "2. Drugi ustęp."
    )

    response = diff(version_a, version_b)

    renumbered = [c for c in response.changes if c.change_type == "RENUMBERED"]
    assert len(renumbered) == 1
    assert (renumbered[0].previous_ref, renumbered[0].article_ref) == ("Art. 1", "Art. 2")
    # Ustępy nie mogą pojawić się jako osobne zmiany.
    assert not [c for c in response.changes if "ust." in c.article_ref]


def test_jednostka_przeniesiona_i_zmieniona_nie_jest_zgadywana() -> None:
    """Świadoma granica: przenumerowanie wykrywamy wyłącznie po identycznej treści.
    Dopasowanie rozmyte wymagałoby progu podobieństwa, którego nie da się uzasadnić
    (ADR 0003), a błędne powiązanie oznaczałoby fałszywe „to tylko przenumerowanie”."""
    version_a = "Art. 1. Wstęp.\nArt. 2. Kary wynoszą do 10 mln zł."
    version_b = "Art. 1. Wstęp.\nArt. 2. Nowy przepis.\nArt. 3. Kary wynoszą do 2 mln zł."

    response = diff(version_a, version_b)

    assert not [c for c in response.changes if c.change_type == "RENUMBERED"]
    assert response.significant_changes_count == len(response.changes)


def test_niejednoznaczna_tresc_nie_jest_wiazana() -> None:
    """Dwie jednostki o identycznej treści nie pozwalają wskazać, która została przeniesiona.
    Bez jednoznaczności nie zgadujemy."""
    version_a = "Art. 1. Powtarzalna treść.\nArt. 2. Powtarzalna treść."
    version_b = "Art. 1. Nowy wstęp.\nArt. 2. Powtarzalna treść.\nArt. 3. Powtarzalna treść."

    response = diff(version_a, version_b)

    assert not [c for c in response.changes if c.change_type == "RENUMBERED"]


# --- Korelacja z uwagami RCL -------------------------------------------------------------


def test_uwaga_do_glebokiej_jednostki_wiaze_sie_dokladnie() -> None:
    zmieniony = AKT.replace("próg wynosi 2000 kWh;", "próg wynosi 2500 kWh;")
    comments = [
        {
            "id": "rcl_007",
            "article_ref": "Art. 2 ust. 2 pkt 2 lit. b",
            "text": "Wnosimy o podniesienie progu dla pozostałych gospodarstw.",
            "submitter": "Federacja Konsumentów",
        }
    ]

    response = diff(AKT, zmieniony, comments)

    zmiana = response.changes[0]
    assert zmiana.consultation_comment_id == "rcl_007"
    assert zmiana.correlation_confidence == 1.0
    assert zmiana.correlation_method == "article_ref_exact"


def test_uwaga_do_artykulu_wiaze_sie_slabiej_niz_do_jednostki() -> None:
    """Uwaga wskazująca „Art. 2”, gdy zmieniła się litera w punkcie, jest sygnałem słabszym
    niż odwołanie wprost. Pewność to udział wskazanych poziomów w ścieżce jednostki —
    liczba wyprowadzona z danych, a nie stała wpisana w kod."""
    zmieniony = AKT.replace("próg wynosi 2000 kWh;", "próg wynosi 2500 kWh;")
    comments = [
        {
            "id": "rcl_008",
            "article_ref": "Art. 2",
            "text": "Uwagi ogólne do artykułu drugiego.",
            "submitter": "Izba Gospodarcza",
        }
    ]

    response = diff(AKT, zmieniony, comments)

    zmiana = response.changes[0]
    assert zmiana.consultation_comment_id == "rcl_008"
    assert zmiana.correlation_method == "article_ref_ancestor"
    # Ścieżka „Art. 2 ust. 2 pkt 2 lit. b” ma 4 poziomy, uwaga wskazuje 1.
    assert zmiana.correlation_confidence == 0.25
