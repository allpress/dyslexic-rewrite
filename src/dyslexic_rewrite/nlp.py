"""spaCy loading and small shared helpers."""

from __future__ import annotations

import functools
import json
from importlib import resources
from typing import Any

_MODELS = {"en": "en_core_web_sm"}


@functools.lru_cache(maxsize=None)
def get_nlp(language: str = "en"):
    import spacy

    model = _MODELS.get(language, "en_core_web_sm")
    try:
        nlp = spacy.load(model)
    except OSError as e:  # pragma: no cover
        raise SystemExit(
            f"spaCy model '{model}' is not installed.\n"
            f"Run:  python -m spacy download {model}"
        ) from e
    if "paragraph_breaks" not in nlp.pipe_names:
        nlp.add_pipe("paragraph_breaks", before="parser")
    return nlp


def _paragraph_breaks(doc):
    """A blank line always ends a sentence, so a heading never merges with the paragraph below it."""
    for i, tok in enumerate(doc[:-1]):
        if tok.is_space and tok.text.count("\n") >= 2:
            doc[i + 1].is_sent_start = True
    return doc


try:  # register once; harmless if spaCy is missing (get_nlp reports that properly)
    from spacy.language import Language as _Language

    if "paragraph_breaks" not in _Language.factories:
        _Language.component("paragraph_breaks", func=_paragraph_breaks)
except Exception:  # pragma: no cover
    pass


@functools.lru_cache(maxsize=None)
def load_data(name: str) -> dict[str, Any]:
    path = resources.files("dyslexic_rewrite").joinpath("data", name)
    return json.loads(path.read_text(encoding="utf-8"))


CONTENT_POS = {"NOUN", "VERB", "ADJ", "ADV", "PROPN"}


def is_content(tok) -> bool:
    return tok.pos_ in CONTENT_POS and tok.is_alpha


def zipf(word: str, language: str = "en") -> float:
    from wordfreq import zipf_frequency

    return zipf_frequency(word, language)
