from .base import Trigger
from .lexical import (
    detect_heteronyms, detect_phrasal, detect_ambiguity, detect_personal, detect_rare, detect_long,
)
from .phonetic import detect_phonetic
from .syntax import detect_syntax

DETECTORS = {
    "personal": detect_personal,
    "ambiguity": detect_ambiguity,
    "phrasal": detect_phrasal,
    "heteronym": detect_heteronyms,
    "phonetic": detect_phonetic,
    "rare": detect_rare,
    "long": detect_long,
    "syntax": detect_syntax,
}

__all__ = ["Trigger", "DETECTORS"]
