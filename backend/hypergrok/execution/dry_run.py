"""Records the order that would have been sent. Sends nothing."""

from __future__ import annotations

from hypergrok.execution.adapter import ExecutionResult, Phase1Adapter


class DryRunAdapter(Phase1Adapter):
    name = "dry_run"
    transmits = False

    def execute(self, would_send: dict) -> ExecutionResult:
        self._refuse_transmission()
        payload = {
            "adapter": self.name,
            "transmitted": False,
            "note": "Recorded only. Nothing was signed or sent.",
            "would_send": would_send,
        }
        return ExecutionResult(
            adapter=self.name,
            transmitted=False,
            status="recorded",
            payload=payload,
            detail="dry run recorded",
        )
