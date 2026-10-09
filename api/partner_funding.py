"""Inbound partner funding webhook — licensed processor credits owner chip.

SynTrends does not take cards. A partner (after entity + counsel) POSTs a
signed event when USD has cleared. This module verifies HMAC and returns a
normalized credit. Enabling live money still requires that partner; the
route is dark until PARTNER_FUNDING_SECRET is set.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Mapping


class PartnerFundingError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class PartnerFundingEvent:
    owner_id: str
    amount: float
    currency: str
    external_id: str
    event: str


def _header(headers: Mapping[str, str], name: str) -> str:
    want = name.lower()
    for key, value in headers.items():
        if key.lower() == want:
            return value
    return ""


def verify_partner_webhook(
    secret: str,
    headers: Mapping[str, str],
    raw_body: bytes,
    *,
    now: float | None = None,
) -> PartnerFundingEvent:
    if not secret:
        raise PartnerFundingError("partner funding is not configured", status_code=404)
    sig_header = _header(headers, "ST-Partner-Signature")
    if not sig_header:
        raise PartnerFundingError("missing ST-Partner-Signature", status_code=401)
    parts: dict[str, str] = {}
    for chunk in sig_header.split(","):
        if "=" not in chunk:
            continue
        k, v = chunk.split("=", 1)
        parts[k.strip()] = v.strip()
    timestamp = parts.get("t")
    provided = parts.get("v1")
    if not timestamp or not provided:
        raise PartnerFundingError("malformed ST-Partner-Signature", status_code=401)
    try:
        ts_i = int(timestamp)
    except ValueError as exc:
        raise PartnerFundingError("invalid timestamp in ST-Partner-Signature", status_code=401) from exc
    clock = time.time() if now is None else now
    if abs(clock - ts_i) > 300:
        raise PartnerFundingError("webhook timestamp outside tolerance window", status_code=401)
    try:
        body_text = raw_body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PartnerFundingError("webhook body is not utf-8", status_code=401) from exc
    signed = f"{timestamp}.{body_text}"
    expected = hmac.new(secret.encode("utf-8"), signed.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, provided):
        raise PartnerFundingError("signature mismatch", status_code=401)
    try:
        body = json.loads(body_text)
    except json.JSONDecodeError as exc:
        raise PartnerFundingError("webhook body is not valid JSON", status_code=400) from exc
    event_name = str(body.get("event") or "")
    if event_name != "funding.credited":
        raise PartnerFundingError(f"unsupported event {event_name!r}", status_code=400)
    owner_id = str(body.get("owner_id") or "").strip()
    external_id = str(body.get("external_id") or "").strip()
    currency = str(body.get("currency") or "USD").strip().upper()
    try:
        amount = float(body.get("amount"))
    except (TypeError, ValueError) as exc:
        raise PartnerFundingError("amount must be a number", status_code=400) from exc
    if not owner_id:
        raise PartnerFundingError("owner_id is required", status_code=400)
    if not external_id:
        raise PartnerFundingError("external_id is required", status_code=400)
    if currency != "USD":
        raise PartnerFundingError("only USD funding is accepted", status_code=400)
    if amount <= 0:
        raise PartnerFundingError("amount must be positive", status_code=400)
    return PartnerFundingEvent(
        owner_id=owner_id,
        amount=amount,
        currency=currency,
        external_id=external_id,
        event=event_name,
    )
