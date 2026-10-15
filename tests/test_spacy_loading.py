import sys
import types

import pytest

import memory.graph as graph


@pytest.fixture
def fake_spacy(monkeypatch):
    """A spaCy whose model is not installed; records load and download attempts."""
    calls = {"load": 0, "download": 0}

    def load(name):
        calls["load"] += 1
        raise OSError(f"[E050] Can't find model '{name}'")

    def download(name):
        calls["download"] += 1

    spacy = types.ModuleType("spacy")
    spacy.load = load
    cli = types.ModuleType("spacy.cli")
    dl = types.ModuleType("spacy.cli.download")
    dl.download = download
    monkeypatch.setitem(sys.modules, "spacy", spacy)
    monkeypatch.setitem(sys.modules, "spacy.cli", cli)
    monkeypatch.setitem(sys.modules, "spacy.cli.download", dl)
    monkeypatch.setattr(graph, "_nlp", None)
    monkeypatch.setattr(graph, "_nlp_error", None)
    return calls


def test_missing_model_is_never_downloaded(fake_spacy):
    with pytest.raises(OSError):
        graph._get_nlp()

    assert fake_spacy["download"] == 0


def test_missing_model_is_not_retried_on_every_call(fake_spacy):
    for _ in range(3):
        with pytest.raises(OSError):
            graph._get_nlp()

    assert fake_spacy["load"] == 1


def test_memory_falls_back_to_simple_keywords(fake_spacy):
    from memory.manager import PersistentMemoryManager

    with PersistentMemoryManager(":memory:") as manager:
        keywords = manager._extract_keywords("Deploy the billing service tonight")

    assert "billing" in keywords
    assert fake_spacy["download"] == 0
