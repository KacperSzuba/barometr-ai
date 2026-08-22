"""Parsowanie struktury artykułów prawnych i powiązanie diffa z uwagami RCL (F3)."""

import re

from barometr_ai.domain.advanced_models import LegalDiffRequest, LegalDiffResponse, LegalUnitDiff


class LegalDiffService:
    """Tworzy drzewiasty diff aktów prawnych i koreluje wykreślenia z uwagami z konsultacji."""

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

            matched_comment_id = None
            matched_submitter = None
            confidence = None

            for comment in request.consultation_comments:
                target_art = comment.get("article_ref", "")
                comment_text = comment.get("text", "").lower()
                submitter = comment.get("submitter", "Podmiot zgłaszający")

                if target_art == key or key.lower() in comment_text or (old_t and old_t[:30].lower() in comment_text):
                    matched_comment_id = comment.get("id", "rcl_uwaga_1")
                    matched_submitter = submitter
                    confidence = 0.85
                    break

            changes.append(
                LegalUnitDiff(
                    article_ref=key,
                    change_type=change_type,
                    old_text=old_t,
                    new_text=new_t,
                    consultation_comment_id=matched_comment_id,
                    consultation_submitter=matched_submitter,
                    correlation_confidence=confidence,
                )
            )

        matched_count = sum(1 for c in changes if c.consultation_comment_id is not None)

        return LegalDiffResponse(
            changes=changes,
            significant_changes_count=len(changes),
            matched_consultations_count=matched_count,
        )

    @staticmethod
    def _extract_articles(text: str) -> dict[str, str]:
        """Ekstrahuje słownik: 'Art. X' -> treść artykułu."""
        articles: dict[str, str] = {}
        pattern = re.compile(r"(Art\.\s*\d+[a-z]?\.)", re.IGNORECASE)
        splits = pattern.split(text)

        if len(splits) <= 1:
            if text.strip():
                articles["Art. 1."] = text.strip()
            return articles

        for i in range(1, len(splits), 2):
            art_header = splits[i].strip()
            art_body = splits[i + 1].strip() if i + 1 < len(splits) else ""
            articles[art_header] = art_body

        return articles