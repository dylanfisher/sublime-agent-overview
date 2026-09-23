# Minimal stubs for the Sublime Text 4 plugin API — only what sublime_agent_overview.py uses.
from sublime import View, Window

class WindowCommand:
    window: Window
    def __init__(self, window: Window) -> None: ...

class TextCommand:
    view: View
    def __init__(self, view: View) -> None: ...
