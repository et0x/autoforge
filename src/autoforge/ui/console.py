"""Rich console singleton and shared styles."""

from rich.console import Console
from rich.theme import Theme

THEME = Theme({
    "keep": "bold green",
    "discard": "dim red",
    "crash": "bold red",
    "baseline": "bold cyan",
    "score": "bold yellow",
    "agent": "blue",
    "phase": "dim italic",
    "header": "bold white on dark_blue",
})

console = Console(theme=THEME)
