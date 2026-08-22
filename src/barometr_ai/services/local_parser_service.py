"""Parser uchwał, protokołów, budżetów i MPZP samorządowych (F4 Local)."""

import re

from barometr_ai.domain.enterprise_models import (
    LocalDocType,
    LocalParseRequest,
    LocalParseResponse,
)


class LocalDocumentParserService:
    """Przetwarza niestandardowe dokumenty BIP samorządu terytorialnego (gminy i powiaty)."""

    @staticmethod
    def parse_document(request: LocalParseRequest) -> LocalParseResponse:
        text = request.bip_text

        # 1. Wykrywanie typu dokumentu
        if "plan zagospodarowania" in text.lower() or "mpzp" in text.lower() or "studium" in text.lower():
            doc_type = LocalDocType.MPZP
            is_spatial = True
        elif "budżet" in text.lower() or "dochodach i wydatkach" in text.lower():
            doc_type = LocalDocType.BUDGET_UCHWALA
            is_spatial = False
        elif "protokół" in text.lower() or "sesji rady" in text.lower():
            doc_type = LocalDocType.PROTOKOL_SESJI
            is_spatial = False
        else:
            doc_type = LocalDocType.UCHWALA_RADY
            is_spatial = False

        # 2. Ekstrakcja numeru uchwały (np. Uchwała Nr XIV/120/2026)
        match_num = re.search(r"(Uchwała\s+Nr\s+[A-Z0-9\/]+)", text, re.IGNORECASE)
        res_num = match_num.group(1) if match_num else None

        # 3. Szacowanie kwoty w budżecie
        match_pln = re.search(r"(\d[\d\s,.]*)\s*(?:zł|złotych|PLN)", text)
        budget_impact = None
        if match_pln:
            clean_num = match_pln.group(1).replace(" ", "").replace(",", ".")
            try:
                budget_impact = float(clean_num)
            except ValueError:
                budget_impact = None

        return LocalParseResponse(
            doc_type=doc_type,
            resolution_number=res_num,
            subject=f"Regulacja samorządowa gminy TERYT {request.gmina_teryt}",
            is_spatial_planning=is_spatial,
            budget_impact_pln=budget_impact,
            summary_plain_polish=f"Dokument dotyczący spraw lokalnych ({doc_type.value}) w gminie {request.gmina_teryt}.",
        )