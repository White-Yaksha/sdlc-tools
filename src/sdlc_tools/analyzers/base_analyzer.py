"""Base interface for analyzer plugins."""

from __future__ import annotations

import abc


class BaseAnalyzer(abc.ABC):
    """Base contract for diff analyzers that emit structured signals."""

    @abc.abstractmethod
    def analyze(self, diff: str) -> dict[str, list[str]]:
        """Analyze *diff* and return structured plugin output.

        Expected keys:
        - ``signals``: List of risk or context signals.
        - ``files``: List of changed file paths observed by the analyzer.
        """
