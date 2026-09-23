"""Registry of agent adapters. Adding an agent: write agents/<name>.py, register it here."""

from typing import Dict, List

from ..core.adapter import Adapter
from .claude import ClaudeAdapter

REGISTRY: Dict[str, Adapter] = {a.name: a for a in (ClaudeAdapter(),)}


def installable() -> List[Adapter]:
    return [a for a in REGISTRY.values() if a.can_install]
