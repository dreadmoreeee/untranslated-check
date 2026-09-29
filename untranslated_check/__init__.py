"""Find untranslated or mixed-language text on multilingual websites."""
from __future__ import annotations

__version__ = "1.0.0"
USER_AGENT = f"untranslated-check/{__version__} (+https://github.com/dreadmoreeee/untranslated-check)"

from .langid import Detection, detect  # noqa: E402

__all__ = ["Detection", "detect", "USER_AGENT", "__version__"]
