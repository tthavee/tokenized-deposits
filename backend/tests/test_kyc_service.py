"""Unit tests for KYCService stub."""

from datetime import date

import pytest

from services.kyc import KYCRequest, KYCService


@pytest.fixture
def svc() -> KYCService:
    return KYCService()


def _req(**overrides) -> KYCRequest:
    defaults = dict(
        first_name="Alice",
        last_name="Smith",
        date_of_birth=date(1990, 1, 15),
        national_id="AB1234",
    )
    return KYCRequest(**{**defaults, **overrides})


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------

def test_approves_well_formed_request(svc):
    result = svc.verify(_req())
    assert result.approved is True
    assert result.failure_reason is None


def test_approves_max_length_national_id(svc):
    result = svc.verify(_req(national_id="A" * 20))
    assert result.approved is True


def test_approves_numeric_national_id(svc):
    result = svc.verify(_req(national_id="12345678"))
    assert result.approved is True


# ---------------------------------------------------------------------------
# Rejection — first_name
# ---------------------------------------------------------------------------

def test_rejects_empty_first_name(svc):
    result = svc.verify(_req(first_name=""))
    assert result.approved is False
    assert "first_name" in result.failure_reason


def test_rejects_whitespace_first_name(svc):
    result = svc.verify(_req(first_name="   "))
    assert result.approved is False
    assert "first_name" in result.failure_reason


# ---------------------------------------------------------------------------
# Rejection — last_name
# ---------------------------------------------------------------------------

def test_rejects_empty_last_name(svc):
    result = svc.verify(_req(last_name=""))
    assert result.approved is False
    assert "last_name" in result.failure_reason


def test_rejects_whitespace_last_name(svc):
    result = svc.verify(_req(last_name="   "))
    assert result.approved is False
    assert "last_name" in result.failure_reason


# ---------------------------------------------------------------------------
# Rejection — national_id format
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_id", [
    "AB1",           # too short (< 4 chars)
    "A" * 21,        # too long (> 20 chars)
    "ab1234",        # lowercase not allowed
    "AB 123",        # space not allowed
    "AB-1234",       # hyphen not allowed
    "",              # empty
])
def test_rejects_invalid_national_id(svc, bad_id):
    result = svc.verify(_req(national_id=bad_id))
    assert result.approved is False
    assert "national_id" in result.failure_reason


def test_rejects_exactly_three_chars(svc):
    result = svc.verify(_req(national_id="ABC"))
    assert result.approved is False
