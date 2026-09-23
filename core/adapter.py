"""The interface every agent adapter in agents/ implements."""

from typing import Any, Dict, Optional

from .event import AgentEvent


class Adapter:
    name = ""
    display_name = ""
    # True when install_hooks / uninstall_hooks are implemented.
    can_install = False

    def parse(self, payload: Dict[str, Any]) -> Optional[AgentEvent]:
        """Map a raw payload to an event; None for payloads this plugin ignores.

        Raises ValueError for a payload that is malformed.
        """
        raise NotImplementedError

    def install_hooks(self, port: int) -> str:
        """Install the agent's hooks pointing at `port`; return a one-line summary."""
        raise NotImplementedError

    def uninstall_hooks(self) -> str:
        """Remove only the hooks install_hooks added; return a one-line summary."""
        raise NotImplementedError
