"""dyslexic-rewrite: rewrite text so dyslexic readers can read it faster.

Pipeline:  text -> analyze (find triggers) -> rewrite (defuse them) -> render (show, with originals on demand)
Profiles:  general -> by dyslexia type -> tuned to one reader from their own writing and speech.
"""

from .analyze import analyze
from .profile import ReaderProfile, load_profile
from .rewrite.engine import rewrite

__version__ = "0.6.0"
__all__ = ["ReaderProfile", "load_profile", "analyze", "rewrite", "__version__"]
