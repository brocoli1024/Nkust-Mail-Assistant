"""Provider contract: callers never depend on a specific AI vendor SDK."""
from typing import Protocol


class AIError(RuntimeError):
    """Safe to display: never include provider response bodies or credentials."""


class AISetupRequired(AIError):
    pass


class AnalysisProvider(Protocol):
    name: str
    model: str

    def generate(self, system: str, payload: dict, schema: dict) -> str:
        """Return a JSON string. Raise AIError for connection/provider failures."""
        ...
