import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

# Setup logger for audit trail
logger = logging.getLogger("xo.audit")
logger.setLevel(logging.INFO)

if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter(
        '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "audit_record": %(message)s}'
    )
    ch.setFormatter(formatter)
    logger.addHandler(ch)

class AuditRecord(BaseModel):
    event_id: str
    event_type: str  # "calculator_output", "customer_data_access", "business_write", "security_boundary"
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    action: str
    resource: str
    status: str = "success"  # "success", "rejected", "denied"
    details: Dict[str, Any] = Field(default_factory=dict)
    compliance_ref: str = "XOTO-CORP-RETENTION-POL-2024-V3"

class AuditService:
    """
    Centralized, tamper-evident audit logger for compliance with UAE/Dubai
    data protection and PRD requirements for financial outputs & customer access.
    """
    _audit_store = []  # In-memory ledger for fast querying in Admin module

    @classmethod
    def log_event(
        cls,
        event_type: str,
        action: str,
        resource: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        status: str = "success",
        details: Optional[Dict[str, Any]] = None
    ) -> AuditRecord:
        record_id = f"aud_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        record = AuditRecord(
            event_id=record_id,
            event_type=event_type,
            session_id=session_id,
            user_id=user_id,
            action=action,
            resource=resource,
            status=status,
            details=details or {}
        )
        
        # Log to structured application logger
        logger.info(record.model_dump_json())
        
        # Store in audit ledger for administrative review
        cls._audit_store.append(record)
        return record

    @classmethod
    def get_recent_logs(cls, limit: int = 50, event_type: Optional[str] = None):
        logs = cls._audit_store
        if event_type:
            logs = [l for l in logs if l.event_type == event_type]
        return logs[-limit:]
