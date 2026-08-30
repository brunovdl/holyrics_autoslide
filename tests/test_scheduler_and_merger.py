"""Testes para o ChunkScheduler e TranscriptMerger."""
import numpy as np
from app.transcription.buffer import AudioRingBuffer
from app.transcription.scheduler import ChunkScheduler
from app.transcription.merger import TranscriptMerger


def test_chunk_scheduler_samples_advance():
    """Valida que o scheduler avança apenas com a quantidade correta de amostras novas."""
    ring = AudioRingBuffer(max_seconds=10.0, sample_rate=16000)
    scheduler = ChunkScheduler(ring, window_duration=2.5, hop_duration=0.8, sample_rate=16000)

    # Inicialmente vazio
    assert not scheduler.has_new_chunk()
    assert scheduler.get_chunk_for_inference() is None

    # Escreve 0.4s de áudio (6400 amostras < hop de 12800)
    ring.write(np.ones(6400, dtype=np.float32))
    assert not scheduler.has_new_chunk()
    assert scheduler.get_chunk_for_inference() is None

    # Escreve mais 0.5s de áudio (total 0.9s > hop de 0.8s)
    ring.write(np.ones(8000, dtype=np.float32))
    assert scheduler.has_new_chunk()

    chunk = scheduler.get_chunk_for_inference()
    assert chunk is not None
    assert len(chunk) == int(2.5 * 16000) or len(chunk) == 14400
    assert not scheduler.has_new_chunk()


def test_transcript_merger_overlap_deduplication():
    """Valida deduplicação inteligente de trechos sobrepostos no TranscriptMerger."""
    merger = TranscriptMerger(max_history_seconds=15.0)

    # Chunk 1
    merger.add_transcription("Aquele que acalma", timestamp=100.0)
    assert merger.get_slide_window_text(4.0) == "Aquele que acalma"

    # Chunk 2 com sobreposição de 'que acalma'
    merger.add_transcription("que acalma o vento", timestamp=100.8)
    assert merger.get_slide_window_text(4.0) == "Aquele que acalma o vento"

    # Chunk 3 com sobreposição de 'o vento'
    merger.add_transcription("o vento e o mar", timestamp=101.6)
    assert merger.get_slide_window_text(4.0) == "Aquele que acalma o vento e o mar"

    # Limpeza atômica
    merger.clear()
    assert merger.get_slide_window_text(4.0) == ""


def test_chunk_scheduler_backlog_drop_latest_wins():
    """Valida que backlog acumulado de 2 hops e 5 hops é descartado em prol do áudio mais recente."""
    ring = AudioRingBuffer(max_seconds=15.0, sample_rate=16000)
    scheduler = ChunkScheduler(ring, window_duration=2.5, hop_duration=0.8, sample_rate=16000)

    # Escreve 4.0s de áudio (5 hops acumulados de uma vez)
    samples_5_hops = int(4.0 * 16000)
    ring.write(np.ones(samples_5_hops, dtype=np.float32))

    assert scheduler.has_new_chunk()
    chunk = scheduler.get_chunk_for_inference()
    assert chunk is not None
    # Como acumulou 5 hops e processou 1, descartou 4 hops
    assert scheduler.dropped_chunks == 4

    # Após entregar o áudio do presente, o cursor aponta para o presente e não há chunk imediato sem novas amostras
    assert not scheduler.has_new_chunk()
    assert scheduler.get_chunk_for_inference() is None
