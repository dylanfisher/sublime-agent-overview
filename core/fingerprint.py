"""Content digests of source files, to tell whether the code running is the code on disk."""

import hashlib
from typing import Dict, Iterable, List

DIGEST_LENGTH = 12


def digest(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()[:DIGEST_LENGTH]


def digests(paths: Iterable[str]) -> Dict[str, str]:
    return {path: digest(path) for path in paths}


def changed(loaded: Dict[str, str]) -> List[str]:
    """The paths in `loaded` whose file on disk no longer has the digest it was loaded with."""
    return sorted(path for path, was in loaded.items() if digest(path) != was)
