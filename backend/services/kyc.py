"""
Stub KYC service — approves all well-formed requests.

A request is considered well-formed when:
  - first_name and last_name are non-empty strings
  - national_id consists of 4–20 uppercase alphanumeric characters
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class KYCRequest:
    first_name: str
    last_name: str
    date_of_birth: date
    national_id: str


@dataclass
class KYCResult:
    approved: bool
    failure_reason: Optional[str] = None


_NATIONAL_ID_RE = re.compile(r"^[A-Z0-9]{4,20}$")


class KYCService:
    """Stub implementation — approves all well-formed requests."""

    def verify(self, request: KYCRequest) -> KYCResult:
        if not request.first_name.strip():
            return KYCResult(approved=False, failure_reason="first_name is required")
        if not request.last_name.strip():
            return KYCResult(approved=False, failure_reason="last_name is required")
        if not _NATIONAL_ID_RE.match(request.national_id):
            return KYCResult(
                approved=False,
                failure_reason="national_id must be 4–20 uppercase alphanumeric characters",
            )
        return KYCResult(approved=True)
