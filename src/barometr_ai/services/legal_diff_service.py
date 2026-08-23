"""Parsowanie struktury artykułów prawnych i powiązanie diffa z uwagami RCL (F3)."""

import re

from barometr_ai.domain.advanced_models import (
    LegalDiffRequest,
    LegalDiffResponse,
    LegalUnitDiff,
)

_ARTICLE_HEADER = re.compile(r"(Art\.\s*\d+[a-z]?\.)", re.IGNORECASE)
_WORD = re.compile(r"[0-9a-ząćęłńóśźż]{4,}", re.IGNORECASE)

#: Minimalne pokrycie leksykalne, poniżej którego uwagi nie wiążemy ze zmianą.
_MIN_OVERLAP = 0.15


class LegalDiffService:
    """Tworzy diff aktów prawnych i koreluje zmiany z uwagami z konsultacji.

    Świadome ograniczenie: podział sięga wyłącznie poziomu artykułu. Zadanie F3 wymaga diffa
    drzewiastego (artykuł → ustęp → punkt → litera) oraz wykrywania przenumerowania —
    stąd wartość `RENUMBERED` w kontrakcie nie jest jeszcze zwracana.
    """

    @classmethod
    def compare_and_correlate(cls, request: LegalDiffRequest) -> LegalDiffResponse:
        units_a = cls._extract_articles(request.version_a_text)
        units_b = cls._extract_articles(request.version_b_text)

        all_keys = sorted(set(units_a.keys()) | set(units_b.keys()))
        changes: list[LegalUnitDiff] = []

        for key in all_keys:
            old_t = units_a.get(key, "").strip()
            new_t = units_b.get(key, "").strip()

            if not old_t and new_t:
                change_type = "ADDED"
            elif old_t and not new_t:
                change_type = "DELETED"
            elif old_t != new_t:
                change_type = "MODIFIED"
            else:
                continue

            match = cls._best_matching_comment(request.consultation_comments, key, old_t, new_t)
            changes.append(
                LegalUnitDiff(
                    article_ref=key,
                    change_type=change_type,
                    old_text=old_t,
                    new_text=new_t,
                    consultation_comment_id=match[0] if match else None,
                    consultation_submitter=match[1] if match else None,
                    correlation_confidence=match[2] if match else None,
                    correlation_method=match[3] if match else None,
                )
            )

        return LegalDiffResponse(
            changes=changes,
            significant_changes_count=len(changes),
            matched_consultations_count=sum(
                1 for change in changes if change.consultation_comment_id is not None
            ),
        )

    @classmethod
    def _best_matching_comment(
        cls, comments: list[dict[str, str]], key: str, old_text: str, new_text: str
    ) -> tuple[str, str, float, str] | None:
        """Wybiera najlepiej dopasowaną uwagę i zwraca policzoną pewność powiązania.

        Poprzednia wersja brała pierwszą uwagę spełniającą dowolny z trzech warunków
        i przypisywała jej stałą pewność 0,85 — niezależnie od tego, czy trafienie było
        dokładnym odwołaniem do artykułu, czy przypadkowym podciągiem.
        """
        best: tuple[str, str, float, str] | None = None

        for comment in comments:
            comment_id = comment.get("id", "")
            submitter = comment.get("submitter", "")
            text = comment.get("text", "")
            if not comment_id:
                continue

            if cls._normalize_ref(comment.get("article_ref", "")) == cls._normalize_ref(key):
                # Jawne odwołanie do jednostki redakcyjnej — najmocniejszy dostępny sygnał.
                return comment_id, submitter, 1.0, "article_ref_exact"

            overlap = cls._lexical_overlap(text, f"{old_text} {new_text}")
            if overlap >= _MIN_OVERLAP and (best is None or overlap > best[2]):
                best = (comment_id, submitter, round(overlap, 3), "lexical_overlap")

        return best

    @staticmethod
    def _normalize_ref(ref: str) -> str:
        return re.sub(r"\s+", "", ref).lower().rstrip(".")

    @staticmethod
    def _lexical_overlap(comment_text: str, article_text: str) -> float:
        """Udział znaczących słów uwagi, które występują w treści zmienionego artykułu."""
        comment_words = {word.lower() for word in _WORD.findall(comment_text)}
        if not comment_words:
            return 0.0
        article_words = {word.lower() for word in _WORD.findall(article_text)}
        return len(comment_words & article_words) / len(comment_words)

    @staticmethod
    def _extract_articles(text: str) -> dict[str, str]:
        """Ekstrahuje słownik: 'Art. X' -> treść artykułu.

        Powtórzony nagłówek doklejany jest do poprzedniej treści zamiast ją nadpisywać —
        wcześniej drugie wystąpienie kasowało pierwsze bez śladu.
        """
        articles: dict[str, str] = {}
        splits = _ARTICLE_HEADER.split(text)

        if len(splits) <= 1:
            if text.strip():
                articles["Art. 1."] = text.strip()
            return articles

        for i in range(1, len(splits), 2):
            header = splits[i].strip()
            body = splits[i + 1].strip() if i + 1 < len(splits) else ""
            if header in articles:
                articles[header] = f"{articles[header]}\n{body}".strip()
            else:
                articles[header] = body

        return articles
