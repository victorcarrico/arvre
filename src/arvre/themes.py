"""Colour palettes for the session graph."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    name: str
    connector: str  # tree and flowchart lines
    bullet: str
    name_style: str  # session names
    meta: str  # age, counts, parent arrow
    border: str  # flowchart box frames
    selected: str  # the highlighted row or box
    accent: str  # key letters in the status line

    def style(self, role: str, selected: bool = False) -> str:
        if selected:
            return self.selected
        return {
            "connector": self.connector,
            "bullet": self.bullet,
            "name": self.name_style,
            "meta": self.meta,
            "border": self.border,
        }.get(role, "")


THEMES: dict[str, Theme] = {
    theme.name: theme
    for theme in [
        Theme(
            name="classic",
            connector="dim",
            bullet="",
            name_style="bold",
            meta="dim",
            border="",
            selected="reverse",
            accent="bold",
        ),
        Theme(
            name="ocean",
            connector="#4a86b8",
            bullet="#5fd7ff",
            name_style="bold #e6f1ff",
            meta="#7f98b5",
            border="#4a86b8",
            selected="bold #0b1d2e on #5fd7ff",
            accent="bold #5fd7ff",
        ),
        Theme(
            name="forest",
            connector="#5f8f5f",
            bullet="#a6e3a1",
            name_style="bold #d8f3dc",
            meta="#8aa58a",
            border="#5f8f5f",
            selected="bold #0d2b1a on #a6e3a1",
            accent="bold #a6e3a1",
        ),
        Theme(
            name="sunset",
            connector="#c26a5a",
            bullet="#ffb86c",
            name_style="bold #ffe6cc",
            meta="#c9a38f",
            border="#e07a5f",
            selected="bold #2b1420 on #ffb86c",
            accent="bold #ffb86c",
        ),
    ]
}
THEME_ORDER = list(THEMES)
