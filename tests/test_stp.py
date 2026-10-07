"""Tests for STP/1.0 Agent Text Protocol encode/decode round-trips."""

from __future__ import annotations

import pytest

from chain.aicoin import create_aicoin
from chain.block import Block
from chain.clock import ManualClock
from chain.engine import SynTrendsDemo
from chain.freeze import FreezeState
from chain.orders import Fill, PostFreezeOrder
from chain.seepnews import Post
from chain.stp import (
    STP_VERSION,
    ParsedAICoinLaunch,
    ParsedAgent,
    ParsedBlock,
    ParsedError,
    ParsedFreezeEvent,
    ParsedHeader,
    ParsedLeaderboard,
    ParsedMeta,
    ParsedOrderBook,
    ParsedPostFreezeOrder,
    ParsedSeepnews,
    ParsedTicker,
    ParsedTrade,
    ParsedWallet,
    STPEmitter,
    STPParseError,
    encode_aicoin_launch,
    encode_agent_deposit,
    encode_agent_register,
    encode_block,
    encode_error,
    encode_freeze_state,
    encode_header,
    encode_leaderboard,
    encode_meta,
    encode_orderbook,
    encode_pfo,
    encode_seepnews,
    encode_ticker,
    encode_trade,
    encode_wallet_coin,
    encode_wallet_fiat,
    parse_line,
    parse_stream,
    reencode,
)


def _coin(clock: ManualClock | None = None):
    return create_aicoin("GEM", "Gemstone", "founder", 10_000, 1_000, 0.10, clock=clock or ManualClock(0.0))


def _roundtrip(line: str):
    record = parse_line(line)
    return record, reencode(record)


def test_header_roundtrip():
    record, back = _roundtrip(encode_header())
    assert isinstance(record, ParsedHeader)
    assert record.version == STP_VERSION
    assert back == STP_VERSION


def test_meta_roundtrip():
    line = encode_meta(1_700_000_000.0, 3, 2)
    record, back = _roundtrip(line)
    assert isinstance(record, ParsedMeta)
    assert record.agents == 3
    assert record.coins == 2
    assert back == line


def test_ticker_roundtrip_with_and_without_fee():
    coin = _coin()
    line = encode_ticker(coin, ts=100.0, fee_pct=0.01)
    record, back = _roundtrip(line)
    assert isinstance(record, ParsedTicker)
    assert record.ticker == "GEM"
    assert record.price == pytest.approx(coin.price)
    assert record.fee_pct == pytest.approx(0.01)
    assert back == line

    line_no_fee = encode_ticker(coin, ts=100.0)
    record2, back2 = _roundtrip(line_no_fee)
    assert record2.fee_pct is None
    assert back2 == line_no_fee


def test_orderbook_roundtrip():
    coin = _coin()
    line = encode_orderbook(coin, ts=200.0)
    record, back = _roundtrip(line)
    assert isinstance(record, ParsedOrderBook)
    assert record.ticker == "GEM"
    assert record.bid > 0
    assert record.ask > 0
    assert record.ask >= record.bid
    assert back == line


def test_freeze_event_roundtrip():
    clock = ManualClock(0.0)
    coin = create_aicoin("GEM", "Gem", "f", 10_000, 1_000, 0.1, cooldown_seconds=10.0, clock=clock)
    coin.freeze.tick(coin.price * 12)
    line = encode_freeze_state(coin, ts=300.0, clock=clock)
    record, back = _roundtrip(line)
    assert isinstance(record, ParsedFreezeEvent)
    assert record.event == "freeze_active"
    assert record.ceil == pytest.approx(coin.freeze.ceiling)
    assert back == line


def test_wallet_fiat_and_coin_roundtrip():
    from chain.cash import CASH_KIND, CASH_UNIT

    line_fiat = encode_wallet_fiat("agent-a", 5000.0)
    rec_fiat, back_fiat = _roundtrip(line_fiat)
    assert isinstance(rec_fiat, ParsedWallet)
    assert rec_fiat.fiat == pytest.approx(5000.0)
    assert rec_fiat.unit == CASH_UNIT
    assert rec_fiat.cash_kind == CASH_KIND
    assert "UNIT=SYNTRENDS" in line_fiat
    assert "KIND=chip" in line_fiat
    assert back_fiat == line_fiat


def test_legacy_wallet_fiat_line_defaults_to_syntrends_chip():
    rec = parse_line("ST/W AGENT=a FIAT=1.0")
    assert isinstance(rec, ParsedWallet)
    assert rec.unit == "SYNTRENDS"
    assert rec.cash_kind == "chip"

    line_coin = encode_wallet_coin("agent-a", "GEM", 123.456)
    rec_coin, back_coin = _roundtrip(line_coin)
    assert rec_coin.ticker == "GEM"
    assert rec_coin.balance == pytest.approx(123.456)
    assert back_coin == line_coin


def test_agent_register_and_deposit_roundtrip():
    reg = encode_agent_register("agent-a", 1.0)
    rec, back = _roundtrip(reg)
    assert isinstance(rec, ParsedAgent)
    assert rec.action == "register"
    assert back == reg

    dep = encode_agent_deposit("agent-a", 250.0, 2.0)
    rec2, back2 = _roundtrip(dep)
    assert rec2.action == "deposit"
    assert rec2.deposit == pytest.approx(250.0)
    assert rec2.unit == "SYNTRENDS"
    assert "UNIT=SYNTRENDS" in dep
    assert back2 == dep


def test_aicoin_launch_roundtrip():
    coin = _coin()
    line = encode_aicoin_launch(coin, ts=50.0)
    record, back = _roundtrip(line)
    assert isinstance(record, ParsedAICoinLaunch)
    assert record.ticker == "GEM"
    assert record.name == "Gemstone"
    assert record.launch == pytest.approx(coin.launch_price)
    assert back == line


def test_trade_roundtrip():
    fill = Fill(
        order_id="oid-1", agent_id="trader-a", coin_id="cid-1",
        side="buy", fiat_amount=200.0, coin_amount=168.76,
        fee_paid=0.02, price_after=1.264013, timestamp=100.0,
    )
    line = encode_trade(fill, "GEM", ts=100.0)
    record, back = _roundtrip(line)
    assert isinstance(record, ParsedTrade)
    assert record.side == "BUY"
    assert record.coins == pytest.approx(168.76)
    assert back == line


def test_seepnews_trade_roundtrip():
    post = Post(
        post_id="pid-1", agent_id="trader-a", category="Trade",
        body="BUY 899.92 $GEM for $100.00 (fee $0.01), price now $0.123454",
        mentions=["GEM"], timestamp=100.0,
    )
    line = encode_seepnews(post, "abc123")
    record, back = _roundtrip(line)
    assert isinstance(record, ParsedSeepnews)
    assert record.category == "Trade"
    assert record.agent == "trader-a"
    assert record.extra.get("SIDE") == "BUY"
    assert record.hash == "abc123"
    assert parse_line(back).extra.get("SIDE") == "BUY"


def test_seepnews_system_freeze_roundtrip():
    post = Post(
        post_id="pid-2", agent_id=None, category="Freezes",
        body="$GEM hit a freeze ceiling at $1.124000. Upward orders locked for 10s.",
        mentions=["GEM"], timestamp=200.0,
    )
    record, _ = _roundtrip(encode_seepnews(post, "hashfreeze"))
    assert record.agent == "SYSTEM"
    assert record.extra.get("CEIL") == "1.124000"


def test_leaderboard_roundtrip():
    coins = [_coin(), create_aicoin("DOG", "Dog", "f", 5000, 100, 0.05, clock=ManualClock(0.0))]
    line = encode_leaderboard(coins, "MCAP", ts=1.0)
    record, back = _roundtrip(line)
    assert isinstance(record, ParsedLeaderboard)
    assert len(record.ranks) == 2
    assert record.ranks[0][1] == "GEM"
    assert back == line


def test_pfo_roundtrip():
    order = PostFreezeOrder(
        order_id="pfo-1", agent_id="trader-b", coin_id="cid-gem",
        side="buy", target_price=1.18, amount=500.0, placed_at=100.0, status="pending",
    )
    line = encode_pfo("PLACE", order, "GEM", ts=100.0)
    record, back = _roundtrip(line)
    assert isinstance(record, ParsedPostFreezeOrder)
    assert record.action == "PLACE"
    assert record.target == pytest.approx(1.18)
    assert back == line


def test_block_and_error_roundtrip():
    block = Block(index=1, timestamp=100.0, transactions=[], previous_hash="0" * 64, hash="abc" * 21 + "a")
    line = encode_block(block)
    record, back = _roundtrip(line)
    assert isinstance(record, ParsedBlock)
    assert record.index == 1
    assert back == line

    err = encode_error("FREEZE_REJECT", "buy rejected above ceiling")
    rec_err, back_err = _roundtrip(err)
    assert isinstance(rec_err, ParsedError)
    assert rec_err.code == "FREEZE_REJECT"
    assert back_err == err


def test_parse_stream_skips_blanks_and_comments():
    text = "\n".join([
        "# comment",
        "",
        encode_header(),
        encode_meta(1.0, 1, 1),
    ])
    records = parse_stream(text)
    assert len(records) == 2


def test_parse_line_rejects_empty():
    with pytest.raises(STPParseError):
        parse_line("   ")


def test_emitter_snapshot_contains_core_lines():
    clock = ManualClock(1_700_000_000.0)
    demo = SynTrendsDemo(clock=clock, seepnews_cooldown_seconds=0.0)
    emitter = STPEmitter(demo, agent_id="trader-a")

    demo.register_agent("founder")
    demo.register_agent("trader-a")
    demo.deposit_fiat("founder", 1000)
    demo.deposit_fiat("trader-a", 5000)
    gem = demo.launch_aicoin("GEM", "Gemstone", "founder", 10_000, 1000, 0.1)

    blob = emitter.snapshot()
    records = parse_stream(blob)

    kinds = {type(r).__name__ for r in records}
    assert "ParsedHeader" in kinds
    assert "ParsedMeta" in kinds
    assert "ParsedTicker" in kinds
    assert "ParsedOrderBook" in kinds
    assert "ParsedLeaderboard" in kinds
    assert "ParsedSeepnews" in kinds

    tickers = [r for r in records if isinstance(r, ParsedTicker)]
    assert any(r.ticker == "GEM" for r in tickers)


def test_emitter_on_trade_appends_tx_and_ticker():
    clock = ManualClock(0.0)
    demo = SynTrendsDemo(clock=clock, seepnews_cooldown_seconds=0.0)
    emitter = STPEmitter(demo, agent_id="trader-a")
    demo.register_agent("founder")
    demo.register_agent("trader-a")
    demo.deposit_fiat("founder", 1000)
    demo.deposit_fiat("trader-a", 5000)
    gem = demo.launch_aicoin("GEM", "Gem", "founder", 10_000, 1000, 0.1)
    emitter.stream.clear()

    fill = demo.buy("trader-a", gem.coin_id, 100)
    emitter.on_trade(fill, gem, was_frozen=False)

    records = [parse_line(l) for l in emitter.stream]
    assert any(isinstance(r, ParsedTrade) for r in records)
    assert any(isinstance(r, ParsedTicker) for r in records)
    wallet_lines = [l for l in emitter.stream if l.startswith("ST/W ") and "TICKER=GEM" in l]
    assert wallet_lines


def test_emitter_on_error():
    clock = ManualClock(0.0)
    demo = SynTrendsDemo(clock=clock)
    emitter = STPEmitter(demo)
    line = emitter.on_error("FREEZE_REJECT", "price above ceiling")
    assert isinstance(parse_line(line), ParsedError)


def test_emitter_full_scenario_stream_parseable():
    """End-to-end: demo actions through emitter produce only valid STP lines."""
    clock = ManualClock(1_700_000_000.0)
    demo = SynTrendsDemo(cooldown_seconds=5.0, pfo_timeout_seconds=10.0, seepnews_cooldown_seconds=0.0, clock=clock)
    emitter = STPEmitter(demo, agent_id="trader-a")

    emitter.on_register("founder")
    emitter.on_register("trader-a")
    demo.deposit_fiat("founder", 1000)
    demo.deposit_fiat("trader-a", 20000)
    emitter.on_deposit("founder", 1000)
    emitter.on_deposit("trader-a", 20000)
    gem = demo.launch_aicoin("GEM", "Gem", "founder", 10_000, 1000, 0.1)
    emitter.on_launch(gem)

    fill = demo.buy("trader-a", gem.coin_id, 100)
    emitter.on_trade(fill, gem, was_frozen=False)

    for _ in range(15):
        try:
            f = demo.buy("trader-a", gem.coin_id, 200)
            emitter.on_trade(f, gem, was_frozen=gem.freeze.state == FreezeState.FROZEN)
        except Exception:
            break

    if gem.freeze.state == FreezeState.FROZEN:
        order = demo.place_post_freeze_order("trader-a", gem.coin_id, "buy", gem.freeze.ceiling * 1.02, 100)
        emitter.on_pfo_place(order, gem)
        emitter.on_error("FREEZE_REJECT", "buy blocked during freeze")

    block = demo.mine_block()
    emitter.on_mine(block)

    for line in emitter.stream:
        parse_line(line)  # must not raise

    assert len(emitter.stream) > 10
