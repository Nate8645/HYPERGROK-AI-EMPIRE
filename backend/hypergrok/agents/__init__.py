"""Rule-based desk agents and the orchestrator that runs them in order."""

from hypergrok.agents.catalog import AGENTS, MODE
from hypergrok.agents.orchestrator import Orchestrator

__all__ = ["AGENTS", "MODE", "Orchestrator"]
