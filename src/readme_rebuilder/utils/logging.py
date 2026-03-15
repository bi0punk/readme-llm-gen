from __future__ import annotations

import logging

from rich.console import Console
from rich.logging import RichHandler


_CONSOLE = Console(stderr=True)


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(message)s',
        datefmt='[%X]',
        handlers=[RichHandler(console=_CONSOLE, rich_tracebacks=True, markup=True)],
        force=True,
    )

    # Keep the CLI readable even in verbose mode.
    noisy_loggers = [
        'httpx',
        'httpcore',
        'ollama',
        'urllib3',
    ]
    for name in noisy_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)
