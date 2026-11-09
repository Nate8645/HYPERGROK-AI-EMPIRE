"""Persist a risk decision and the client order id that produced it.

The service does not change a REJECT into a PASS. Duplicate protection is the
unique client order id recorded on first sight.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from hypergrok.domain import OrderIntent, RiskDecision
from hypergrok.events import EventBus
from hypergrok.risk.engine import RiskEngine
from hypergrok.serialize import to_jsonable
from hypergrok.store import DeskStore

logger = logging.getLogger(__name__)


class RiskService:
    def __init__(self, store: DeskStore, engine: RiskEngine, bus: EventBus) -> None:
        self.store = store
        self.engine = engine
        self.bus = bus

    def evaluate(
        self,
        order: OrderIntent,
        now: datetime,
        *,
        case_id: str | None = None,
    ) -> RiskDecision:
        try:
            return self._evaluate(order, now, case_id=case_id, force_duplicate=False)
        except IntegrityError:
            logger.info(
                "duplicate client order id on insert",
                extra={"context": {"client_order_id": order.client_order_id}},
            )
            return self._evaluate(order, now, case_id=case_id, force_duplicate=True)

    def _evaluate(
        self,
        order: OrderIntent,
        now: datetime,
        *,
        case_id: str | None,
        force_duplicate: bool,
    ) -> RiskDecision:
        session: Session = self.store._session()
        try:
            already = force_duplicate or self.store.client_order_exists(session, order.client_order_id)
            seen = {order.client_order_id} if already else set()
            account = self._account_in_session(session, now)
            kill = self._kill_in_session(session)
            decision = self.engine.evaluate(
                order,
                account,
                now=now,
                kill_switch_engaged=kill,
                seen_client_order_ids=seen,
            )
            if not already:
                self.store.insert_client_order(
                    session,
                    client_order_id=order.client_order_id,
                    status=decision.status,
                    now=now,
                )
            payload = to_jsonable(decision)
            self.store.insert_risk_decision(
                session,
                case_id=case_id,
                client_order_id=order.client_order_id,
                status=decision.status,
                reasons=decision.reasons,
                payload=payload,
                now=now,
            )
            event = self.store.insert_event(
                session,
                agent="risk_manager",
                event_type="risk_decision",
                status=decision.status,
                case_id=case_id,
                summary=decision.summary,
                payload={"decision": payload, "implementation": "rule_based"},
                now=now,
            )
            session.commit()
        except IntegrityError:
            session.rollback()
            raise
        finally:
            session.close()
        self.bus.publish(event)
        logger.info(
            "risk decision",
            extra={
                "context": {
                    "status": decision.status,
                    "reasons": decision.reasons,
                    "client_order_id": order.client_order_id,
                    "symbol": order.symbol,
                }
            },
        )
        return decision

    def _account_in_session(self, session: Session, now: datetime):
        row = self.store._account_row(session, now)
        return self.store._account_state(row)

    def _kill_in_session(self, session: Session) -> bool:
        from hypergrok.models import KillSwitchRow

        row = session.get(KillSwitchRow, 1)
        if row is None:
            return True
        return bool(row.engaged)
