import itertools
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.security import mask_name, mask_phone

logger = logging.getLogger("xo.audit")

_PHONE_KEYS = ("phone", "applicant_phone", "contact_phone")
_NAME_KEYS = ("name", "applicant_name", "contact_name", "full_name")
_EMAIL_KEYS = ("email", "contact_email", "applicant_email")


def _mask_details(details: Dict[str, Any]) -> Dict[str, Any]:
    masked: Dict[str, Any] = {}
    for key, value in details.items():
        if key in _PHONE_KEYS:
            masked[key] = mask_phone(value)
        elif key in _NAME_KEYS:
            masked[key] = mask_name(value)
        elif key in _EMAIL_KEYS:
            masked[key] = "***" if value else value
        elif isinstance(value, dict):
            masked[key] = _mask_details(value)
        else:
            masked[key] = value
    return masked


class AuditRecord(BaseModel):
    event_id: str
    event_type: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    action: str
    resource: str
    status: str = "success"
    details: Dict[str, Any] = Field(default_factory=dict)
    compliance_ref: str = Field(default_factory=lambda: settings.COMPANY_RETENTION_POLICY_REF)


class AuditService:
    """Audit trail for calculator outputs, customer-data access and business writes (PRD §7 Auditability).
    Personal data is masked before it is logged or kept in memory."""

    _audit_store: Deque[AuditRecord] = deque(maxlen=5000)
    _counter = itertools.count(1)

    @classmethod
    def log_event(
        cls,
        event_type: str,
        action: str,
        resource: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        status: str = "success",
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditRecord:
        record = AuditRecord(
            event_id=f"aud_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{next(cls._counter)}",
            event_type=event_type,
            session_id=session_id,
            user_id=user_id,
            action=action,
            resource=resource,
            status=status,
            details=_mask_details(details or {}),
        )
        logger.info(record.model_dump_json())
        cls._audit_store.append(record)
        return record

    @classmethod
    def get_recent_logs(cls, limit: int = 50, event_type: Optional[str] = None) -> List[AuditRecord]:
        logs = [r for r in cls._audit_store if not event_type or r.event_type == event_type]
        return logs[-limit:]
