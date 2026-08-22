from barometr_ai.services.chunking_service import ChunkingService


def test_empty_text_returns_empty_chunks() -> None:
    """Test 1: Pusty tekst lub same spacje powinny zwrócić pustą listę."""
    service = ChunkingService()
    chunks = service.split_text(document_id="doc_1", text="    ")
    assert chunks == []

def test_short_text_single_chunk() -> None:
    """Test 2: Tekst krótszy niż target_chunk_size powinien dać dokładnie 1 chunk."""
    service = ChunkingService(target_chunk_size=500)
    text = "Art. 1. Ustawa określa zasady polityki energetycznej państwa."

    chunks = service.split_text(document_id="doc_law_1", text=text)

    # Sprawdzamy liczbę chunków
    assert len(chunks) == 1
    # Sprawdzamy, czy treść chunka zgadza się z tekstem
    assert chunks[0].text == text
    # Sprawdzamy kluczową regułę: czy span poprawnie weryfikuje się z oryginałem
    assert chunks[0].span.validate_against_text(text) is True


def test_long_legal_text_splits_and_preserves_provenance() -> None:
    """Test 3: Długi dokument prawny podzielony na części - żaden chunk nie może mieć błędnych indeksów."""
    service = ChunkingService(target_chunk_size=120, overlap=20)

    long_text = (
        "Art. 1. Ustawa określa warunki rozwoju odnawialnych źródeł energii.\n\n"
        "Art. 2. Użyte w ustawie określenia oznaczają:\n"
        "1) biomasa – substancje pochodzenia biologicznego;\n"
        "2) biogaz – gaz uzyskany z biomasy;\n"
        "3) prosument energii odnawialnej – odbiorca końcowy wytwarzający energię."
    )

    chunks = service.split_text(document_id="doc_oze", text=long_text)

    # Musi powstać więcej niż 1 chunk
    assert len(chunks) > 1

    # SPRAWDZIAN PROWENIENCJI: Każdy chunk musi idealnie pasować do wycinka w long_text
    for chunk in chunks:
        # 1. Metoda validate_against_text musi potwierdzić poprawność
        assert chunk.span.validate_against_text(long_text) is True

        # 2. Wycinamy ręcznie z tekstu po indeksach i sprawdzamy zgodność
        extracted = long_text[chunk.span.char_start:chunk.span.char_end]
        assert extracted == chunk.text
