"""Drzewiasty diff aktów prawnych i powiązanie zmian z uwagami RCL (F3).

Podział idzie przez pełną hierarchię jednostek redakcyjnych z zasad techniki prawodawczej:
**artykuł → ustęp → punkt → litera → tiret**. Poprzednia wersja zatrzymywała się na artykule,
więc zmiana jednego słowa w jednym punkcie oznaczała cały artykuł jako `MODIFIED` i wiązała
z nim wszystkie uwagi z konsultacji.

Porównywana jest **treść własna** jednostki, bez treści jej dzieci. Dzięki temu zmiana w
literze nie zaraża punktu, ustępu i artykułu — raportowana jest najgłębsza jednostka, która
faktycznie się zmieniła, i to do niej wiążą się uwagi.
"""

import re
from dataclasses import dataclass

from barometr_ai.domain.advanced_models import (
    LegalDiffRequest,
    LegalDiffResponse,
    LegalUnitDiff,
)

#: Nagłówek artykułu (ustawy) albo paragrafu (rozporządzenia). Dopuszczony w dowolnym
#: miejscu tekstu, bo akty bywają przekazywane jako jeden akapit bez podziału na wiersze.
_ARTICLE_HEADER = re.compile(r"(Art\.\s*\d+[a-z]?\.|§\s*\d+[a-z]?\.)", re.IGNORECASE)

#: Znaczniki niższych poziomów rozpoznajemy wyłącznie na początku wiersza. Wewnątrz zdania
#: „1." bywa końcem odwołania („zgodnie z art. 5 ust. 1."), a nie nowym ustępem.
_USTEP = re.compile(r"^\s*(\d+[a-z]?)\.\s+")
_PUNKT = re.compile(r"^\s*(\d+[a-z]?)\)\s+")
_LITERA = re.compile(r"^\s*([a-ząćęłńóśźż]{1,2})\)\s+")
_TIRET = re.compile(r"^\s*[-–—]\s+")

_WORD = re.compile(r"[0-9a-ząćęłńóśźż]{4,}", re.IGNORECASE)

#: Minimalne pokrycie leksykalne, poniżej którego uwagi nie wiążemy ze zmianą.
_MIN_OVERLAP = 0.15

_LEVEL_ARTICLE = 0
_LEVEL_USTEP = 1
_LEVEL_PUNKT = 2
_LEVEL_LITERA = 3
_LEVEL_TIRET = 4


@dataclass(frozen=True)
class LegalUnit:
    """Jednostka redakcyjna z pełną ścieżką odniesienia i własną treścią.

    `parts` to ścieżka rozbita na poziomy (`("Art. 2", "ust. 1", "pkt 3")`) — pozwala
    sprawdzić, czy jedna jednostka jest przodkiem drugiej, bez parsowania napisu.
    """

    ref: str
    parts: tuple[str, ...]
    text: str

    @property
    def level(self) -> int:
        return len(self.parts) - 1

    def is_descendant_of(self, other: "LegalUnit") -> bool:
        return len(self.parts) > len(other.parts) and self.parts[: len(other.parts)] == other.parts


@dataclass(frozen=True)
class RenumberedUnit:
    """Jednostka przeniesiona pod inne odniesienie bez zmiany treści.

    `implied=True` oznacza przeniesienie wynikające z przenumerowania jednostki nadrzędnej.
    Taka para jest **rozliczona** (nie wraca do porównania po odniesieniu), ale nie jest
    raportowana osobno — inaczej przesunięcie jednego artykułu generowałoby wpis dla
    każdego jego ustępu, punktu i litery.
    """

    old_ref: str
    new_ref: str
    implied: bool


def normalize_unit_text(text: str) -> str:
    """Kanonizuje treść jednostki do porównań: pojedyncze odstępy, bez brzegowych."""
    return " ".join(text.split())


def parse_legal_units(text: str) -> dict[str, LegalUnit]:
    """Rozkłada akt na jednostki redakcyjne wraz z ich treścią własną.

    Zwraca mapę `ref -> LegalUnit`, gdzie `ref` ma postać kanoniczną zgodną z opisem pola
    `LegalUnitDiff.article_ref`, np. `Art. 4 ust. 2 pkt 3 lit. a`.
    """
    units: dict[str, LegalUnit] = {}

    for article_ref, body in _split_articles(text):
        stack: list[tuple[int, tuple[str, ...]]] = [(_LEVEL_ARTICLE, (article_ref,))]
        _append_text(units, (article_ref,), "")
        current: tuple[str, ...] = (article_ref,)
        tiret_counters: dict[tuple[str, ...], int] = {}

        for line in body.splitlines():
            marker = _classify_line(line, tiret_counters, stack)
            if marker is None:
                _append_text(units, current, line)
                continue

            label, level, remainder = marker
            while len(stack) > 1 and stack[-1][0] >= level:
                stack.pop()
            current = (*stack[-1][1], label)
            stack.append((level, current))
            _append_text(units, current, remainder)

    return units


def _classify_line(
    line: str,
    tiret_counters: dict[tuple[str, ...], int],
    stack: list[tuple[int, tuple[str, ...]]],
) -> tuple[str, int, str] | None:
    """Rozpoznaje znacznik jednostki na początku wiersza. Zwraca (etykieta, poziom, reszta)."""
    if not line.strip():
        return None

    match = _PUNKT.match(line)
    if match:
        return f"pkt {match.group(1)}", _LEVEL_PUNKT, line[match.end() :]

    match = _LITERA.match(line)
    if match:
        return f"lit. {match.group(1)}", _LEVEL_LITERA, line[match.end() :]

    match = _USTEP.match(line)
    if match:
        return f"ust. {match.group(1)}", _LEVEL_USTEP, line[match.end() :]

    match = _TIRET.match(line)
    if match:
        # Tiret nie mają własnej numeracji w tekście — numerujemy je w obrębie rodzica,
        # żeby odniesienie dało się jednoznacznie wskazać.
        parent = next(
            (parts for level, parts in reversed(stack) if level < _LEVEL_TIRET), stack[0][1]
        )
        tiret_counters[parent] = tiret_counters.get(parent, 0) + 1
        return f"tiret {tiret_counters[parent]}", _LEVEL_TIRET, line[match.end() :]

    return None


def _append_text(units: dict[str, LegalUnit], parts: tuple[str, ...], addition: str) -> None:
    ref = " ".join(parts)
    existing = units.get(ref)
    merged = f"{existing.text} {addition}".strip() if existing else addition.strip()
    units[ref] = LegalUnit(ref=ref, parts=parts, text=normalize_unit_text(merged))


def _split_articles(text: str) -> list[tuple[str, str]]:
    """Dzieli akt na artykuły. Powtórzony nagłówek dokleja treść zamiast ją nadpisywać."""
    splits = _ARTICLE_HEADER.split(text)

    if len(splits) <= 1:
        return [("Art. 1", text)] if text.strip() else []

    ordered: list[str] = []
    bodies: dict[str, str] = {}
    for index in range(1, len(splits), 2):
        ref = _canonical_article_ref(splits[index])
        body = splits[index + 1] if index + 1 < len(splits) else ""
        if ref in bodies:
            bodies[ref] = f"{bodies[ref]}\n{body}"
        else:
            bodies[ref] = body
            ordered.append(ref)
    return [(ref, bodies[ref]) for ref in ordered]


def _canonical_article_ref(header: str) -> str:
    """`art.  4 .` → `Art. 4`; `§ 2.` → `§ 2`. Postać zgodna z kontraktem `article_ref`."""
    compact = re.sub(r"\s+", " ", header).strip().rstrip(".")
    if compact.lower().startswith("art"):
        number = compact.split(".", 1)[1].strip() if "." in compact else compact[3:].strip()
        return f"Art. {number}"
    return f"§ {compact.lstrip('§').strip()}"


class LegalDiffService:
    """Tworzy drzewiasty diff aktów prawnych i koreluje zmiany z uwagami z konsultacji."""

    @classmethod
    def compare_and_correlate(cls, request: LegalDiffRequest) -> LegalDiffResponse:
        units_a = parse_legal_units(request.version_a_text)
        units_b = parse_legal_units(request.version_b_text)

        renumbered = cls._detect_renumbering(units_a, units_b)

        changes: list[LegalUnitDiff] = [
            LegalUnitDiff(
                article_ref=moved.new_ref,
                previous_ref=moved.old_ref,
                change_type="RENUMBERED",
                old_text=units_a[moved.old_ref].text,
                new_text=units_b[moved.new_ref].text,
            )
            for moved in renumbered
            if not moved.implied
        ]

        # Jednostki rozliczone jako przeniesione wypadają z porównania po odniesieniu.
        # Odniesienie zwolnione przez przeniesienie może przyjąć nową treść — i wtedy jest
        # to `ADDED`, a nie `MODIFIED` wobec przepisu, który stąd wyszedł.
        remaining_a = {
            ref: unit for ref, unit in units_a.items() if ref not in {m.old_ref for m in renumbered}
        }
        remaining_b = {
            ref: unit for ref, unit in units_b.items() if ref not in {m.new_ref for m in renumbered}
        }

        for ref in sorted(set(remaining_a) | set(remaining_b)):
            old_text = remaining_a[ref].text if ref in remaining_a else ""
            new_text = remaining_b[ref].text if ref in remaining_b else ""

            if ref not in remaining_a:
                change_type = "ADDED"
            elif ref not in remaining_b:
                change_type = "DELETED"
            elif old_text != new_text:
                change_type = "MODIFIED"
            else:
                continue

            unit = remaining_b.get(ref) or remaining_a[ref]
            match = cls._best_matching_comment(
                request.consultation_comments, unit, old_text, new_text
            )
            changes.append(
                LegalUnitDiff(
                    article_ref=ref,
                    change_type=change_type,
                    old_text=old_text,
                    new_text=new_text,
                    consultation_comment_id=match[0] if match else None,
                    consultation_submitter=match[1] if match else None,
                    correlation_confidence=match[2] if match else None,
                    correlation_method=match[3] if match else None,
                )
            )

        return LegalDiffResponse(
            changes=changes,
            # Przenumerowanie nie zmienia treści przepisu, więc nie jest zmianą merytoryczną.
            significant_changes_count=sum(
                1 for change in changes if change.change_type != "RENUMBERED"
            ),
            matched_consultations_count=sum(
                1 for change in changes if change.consultation_comment_id is not None
            ),
        )

    @classmethod
    def _detect_renumbering(
        cls, units_a: dict[str, LegalUnit], units_b: dict[str, LegalUnit]
    ) -> list["RenumberedUnit"]:
        """Wykrywa jednostki przeniesione pod inne odniesienie bez zmiany treści.

        Dopasowanie wyłącznie po **identycznej** treści własnej, i tylko gdy ta treść jest
        unikalna po obu stronach. To nie jest słabszy wariant dopasowania rozmytego, lecz
        model dominującego przypadku: przenumerowanie powstaje przez wstawienie jednostki
        wcześniej, co przesuwa kolejne **bez ich zmiany**.

        Jednostka jednocześnie przeniesiona i zmieniona nie jest z niczym wiązana — zgadywanie
        takiego powiązania wymagałoby progu podobieństwa, którego nie da się uzasadnić
        (por. ADR 0003). Wraca wtedy do porównania po odniesieniu, a wynik zależy od tego, czy
        zwolnione odniesienie zostało ponownie zajęte: jeśli tak, jest to `MODIFIED` pod starym
        odniesieniem i `ADDED` pod nowym; jeśli nie — `DELETED` + `ADDED`.
        """
        by_text_a = cls._unique_by_text(units_a)
        by_text_b = cls._unique_by_text(units_b)

        # Para kwalifikuje się, gdy ta sama treść stoi w obu wersjach pod *innym* odniesieniem.
        # Nie wolno tu zawężać do jednostek nieobecnych po drugiej stronie: przy przesunięciu
        # numeracji odniesienie zwykle istnieje w obu wersjach, tyle że z inną treścią.
        pairs = [
            (by_text_a[text], by_text_b[text])
            for text in sorted(set(by_text_a) & set(by_text_b))
            if by_text_a[text] != by_text_b[text]
        ]

        # Przenumerowanie artykułu przesuwa wszystkie jego dzieci. Raportujemy wtedy sam
        # artykuł — powtarzanie tego dla każdej litery zalałoby odpowiedź szumem. Dzieci
        # pozostają jednak *rozliczone*: gdyby wypadły z puli przeniesionych, wróciłyby
        # do porównania po odniesieniu jako fałszywa para DELETED + ADDED.
        implied: set[tuple[str, str]] = set()
        for old_ref, new_ref in pairs:
            ancestor_old, ancestor_new = units_a[old_ref], units_b[new_ref]
            for other_old, other_new in pairs:
                if (other_old, other_new) == (old_ref, new_ref):
                    continue
                if units_a[other_old].is_descendant_of(ancestor_old) and units_b[
                    other_new
                ].is_descendant_of(ancestor_new):
                    implied.add((other_old, other_new))

        return [
            RenumberedUnit(old_ref=old_ref, new_ref=new_ref, implied=(old_ref, new_ref) in implied)
            for old_ref, new_ref in pairs
        ]

    @staticmethod
    def _unique_by_text(units: dict[str, LegalUnit]) -> dict[str, str]:
        """Mapa treść → ref, wyłącznie dla treści występujących dokładnie raz."""
        counts: dict[str, int] = {}
        for unit in units.values():
            if unit.text:
                counts[unit.text] = counts.get(unit.text, 0) + 1
        return {
            unit.text: unit.ref for unit in units.values() if unit.text and counts[unit.text] == 1
        }

    @classmethod
    def _best_matching_comment(
        cls, comments: list[dict[str, str]], unit: LegalUnit, old_text: str, new_text: str
    ) -> tuple[str, str, float, str] | None:
        """Wybiera najlepiej dopasowaną uwagę i zwraca policzoną pewność powiązania."""
        best: tuple[str, str, float, str] | None = None

        for comment in comments:
            comment_id = comment.get("id", "")
            submitter = comment.get("submitter", "")
            if not comment_id:
                continue

            reference = comment.get("article_ref", "")
            if reference:
                if cls._normalize_ref(reference) == cls._normalize_ref(unit.ref):
                    # Jawne odwołanie do tej samej jednostki — najmocniejszy możliwy sygnał.
                    return comment_id, submitter, 1.0, "article_ref_exact"

                depth = cls._ancestor_depth(reference, unit)
                if depth > 0:
                    # Uwaga wskazuje jednostkę nadrzędną (np. „Art. 2” wobec zmiany w
                    # „Art. 2 ust. 1 pkt 3”). Pewność to udział wskazanych poziomów w
                    # ścieżce jednostki — liczba z danych, nie stała.
                    confidence = depth / len(unit.parts)
                    if best is None or confidence > best[2]:
                        best = (comment_id, submitter, round(confidence, 3), "article_ref_ancestor")
                    continue

            overlap = cls._lexical_overlap(comment.get("text", ""), f"{old_text} {new_text}")
            if overlap >= _MIN_OVERLAP and (best is None or overlap > best[2]):
                best = (comment_id, submitter, round(overlap, 3), "lexical_overlap")

        return best

    @classmethod
    def _ancestor_depth(cls, reference: str, unit: LegalUnit) -> int:
        """Ile początkowych poziomów ścieżki jednostki pokrywa odniesienie z uwagi."""
        reference_parts = reference.split()
        for depth in range(len(unit.parts) - 1, 0, -1):
            prefix = " ".join(unit.parts[:depth])
            if cls._normalize_ref(" ".join(reference_parts)) == cls._normalize_ref(prefix):
                return depth
        return 0

    @staticmethod
    def _normalize_ref(ref: str) -> str:
        return re.sub(r"\s+", "", ref).lower().rstrip(".")

    @staticmethod
    def _lexical_overlap(comment_text: str, unit_text: str) -> float:
        """Udział znaczących słów uwagi, które występują w treści zmienionej jednostki."""
        comment_words = {word.lower() for word in _WORD.findall(comment_text)}
        if not comment_words:
            return 0.0
        unit_words = {word.lower() for word in _WORD.findall(unit_text)}
        return len(comment_words & unit_words) / len(comment_words)
