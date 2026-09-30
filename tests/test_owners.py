"""Unit tests for api/owners.py."""

from __future__ import annotations

import pytest

from api.owners import KYCError, KYCStatus, OwnerError, OwnerRegistry


def test_register_login_and_kyc_flow():
    reg = OwnerRegistry()
    owner = reg.register("alice@example.com", "securepass1")
    session = reg.login("alice@example.com", "securepass1")
    logged_in = reg.lookup_session(session.token)
    assert logged_in.owner_id == owner.owner_id

    with pytest.raises(KYCError):
        reg.can_issue_agent_key(logged_in)

    reg.accept_agreements(owner.owner_id)
    with pytest.raises(KYCError):
        reg.can_issue_agent_key(logged_in)

    reg.accept_syntrendrules(owner.owner_id)
    with pytest.raises(KYCError):
        reg.can_issue_agent_key(logged_in)

    reg.accept_seeprules(owner.owner_id)
    with pytest.raises(KYCError):
        reg.submit_kyc(owner.owner_id, "Alice", "US", attestation=False)

    reg.submit_kyc(owner.owner_id, "Alice", "US", attestation=True)
    assert reg.lookup_session(session.token).kyc_status == KYCStatus.SUBMITTED

    reg.approve_kyc(owner.owner_id)
    approved = reg.lookup_session(session.token)
    reg.can_issue_agent_key(approved)  # no raise
    reg.bind_agent(owner.owner_id, "agent-alice")


def test_syntrendrules_required_before_agent_key():
    reg = OwnerRegistry()
    owner = reg.register("dave@example.com", "password123")
    reg.accept_agreements(owner.owner_id)
    reg.submit_kyc(owner.owner_id, "Dave", "US", attestation=True)
    reg.approve_kyc(owner.owner_id)
    approved = reg.get_owner(owner.owner_id)
    with pytest.raises(KYCError, match="syntrendrules"):
        reg.can_issue_agent_key(approved)


def test_seeprules_required_before_agent_key():
    reg = OwnerRegistry()
    owner = reg.register("carol@example.com", "password123")
    reg.accept_agreements(owner.owner_id)
    reg.submit_kyc(owner.owner_id, "Carol", "US", attestation=True)
    reg.approve_kyc(owner.owner_id)
    approved = reg.get_owner(owner.owner_id)
    reg.accept_syntrendrules(owner.owner_id)
    with pytest.raises(KYCError, match="seeprules"):
        reg.can_issue_agent_key(approved)


def test_duplicate_email_rejected():
    reg = OwnerRegistry()
    reg.register("bob@example.com", "password123")
    with pytest.raises(OwnerError):
        reg.register("bob@example.com", "password456")
