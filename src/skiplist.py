"""Persistent skip list for delisted / bad tickers."""

import json
import os

from src.config import DATA_DIR
from src.logger import get_logger

log = get_logger(__name__)

SKIP_FILE = os.path.join(DATA_DIR, "skip_tickers.json")


def _load() -> set[str]:
    if not os.path.exists(SKIP_FILE):
        return set()
    try:
        with open(SKIP_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save(skip: set[str]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SKIP_FILE, "w") as f:
        json.dump(sorted(skip), f, indent=2)


def get_skip_list() -> set[str]:
    return _load()


def add_to_skip_list(tickers: list[str]) -> None:
    if not tickers:
        return
    skip = _load()
    new = [t for t in tickers if t not in skip]
    if new:
        skip.update(new)
        _save(skip)
        log.info("Added %d tickers to skip list: %s", len(new), new)
        print(f"  Skipping {len(new)} delisted/invalid tickers in future runs: {new}")


def filter_universe(tickers: list[str]) -> list[str]:
    skip = _load()
    if not skip:
        return tickers
    filtered = [t for t in tickers if t not in skip]
    removed = len(tickers) - len(filtered)
    if removed:
        log.debug("Skipped %d tickers from skip list", removed)
        print(f"  Skipping {removed} previously flagged tickers")
    return filtered
