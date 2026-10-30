"""The card format: business-plan's bizplan.opportunities, from the checkout.

That module reads the cards and works out the matrix columns, beside the
decision rules that stay private in business-plan, so it isn't in this
repository or its image. The site imports it from the checkout it shows
(content.py), afresh whenever the checkout moves, so the code that reads a card
comes from the same commit as the card.

The site uses ``FIELDS``, ``read`` and ``rows``. business-plan's
tests/test_opportunity_contract.py checks they stay as the site expects; this
repository's tests run on a stand-in with the same interface
(tests/fixtures/business-plan/).
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

PACKAGE = "bizplan"
MODULE = f"{PACKAGE}.opportunities"

_module: ModuleType | None = None
_from: tuple[Path, str] | None = None  # the checkout and commit it was imported from
_on_path: str | None = None


def load(root: Path, sha: str) -> None:
    """Import the format from the checkout at ``root``, unless it already came from this commit.
    If the import fails, the format imported before stays."""
    global _module, _from, _on_path
    if _from == (root, sha):
        return
    for name in [m for m in sys.modules if m == PACKAGE or m.startswith(f"{PACKAGE}.")]:
        del sys.modules[name]
    if _on_path:
        sys.path.remove(_on_path)
    _on_path = str(root)
    sys.path.insert(0, _on_path)
    importlib.invalidate_caches()
    _module = importlib.import_module(MODULE)
    _from = (root, sha)


def loaded() -> bool:
    return _module is not None


def opp() -> ModuleType:
    """The format imported last."""
    if _module is None:
        raise RuntimeError(f"{MODULE} isn't loaded: Content.now() imports it from the checkout")
    return _module
