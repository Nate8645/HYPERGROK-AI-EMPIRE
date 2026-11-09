"""Dry-run execution only. See `adapter` for the phase-1 boundary."""

from hypergrok.execution.adapter import ExecutionAdapter
from hypergrok.execution.dry_run import DryRunAdapter
from hypergrok.execution.gate import ExecutionGate

__all__ = ["ExecutionAdapter", "DryRunAdapter", "ExecutionGate"]
