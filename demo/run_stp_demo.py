"""STP/1.0 stream demo: same scenario as run_demo but output is agent-native text.

Run from repo root::

    python -m demo.run_stp_demo

Agents would subscribe to lines like these over SSE/WebSocket in Phase B.
Humans never parse this directly; **3rdPS API** chart translators consume it.
"""

from chain.clock import ManualClock
from chain.engine import SynTrendsDemo
from chain.freeze import FreezeState
from chain.orders import OrderError
from chain.stp import STPEmitter

MAX_PUMP_ATTEMPTS = 300


def print_section(title: str) -> None:
    print(f"\n# --- {title} ---")


def main() -> None:
    clock = ManualClock(start=1_700_000_000.0)
    demo = SynTrendsDemo(
        cooldown_seconds=10.0,
        pfo_timeout_seconds=15.0,
        seepnews_cooldown_seconds=0.0,
        clock=clock,
    )
    stp = STPEmitter(demo, agent_id="agent-trader-a")

    founder = "agent-founder"
    trader_a = "agent-trader-a"
    trader_b = "agent-trader-b"

    print_section("cold-start snapshot (empty market)")
    print(stp.snapshot())

    print_section("register agents + deposit fiat")
    for agent in (founder, trader_a, trader_b):
        demo.register_agent(agent)
        stp.on_register(agent)
    demo.deposit_fiat(founder, 1_000)
    demo.deposit_fiat(trader_a, 20_000)
    demo.deposit_fiat(trader_b, 20_000)
    stp.on_deposit(founder, 1_000)
    stp.on_deposit(trader_a, 20_000)
    stp.on_deposit(trader_b, 20_000)
    print(stp.tail(6))

    print_section("launch $GEM")
    gem = demo.launch_aicoin(
        ticker="GEM", name="Gemstone Protocol", creator_agent_id=founder,
        total_supply=10_000, invest_fiat=1_000, pre_own_pct=0.10,
    )
    stp.on_launch(gem)
    print(stp.tail(5))

    print_section("trader-a buys in")
    fill = demo.buy(trader_a, gem.coin_id, 100)
    stp.on_trade(fill, gem, was_frozen=False)
    print(stp.tail(4))

    print_section("pump toward +1024% freeze")
    target = gem.launch_price * 11.24
    was = gem.freeze.state == FreezeState.FROZEN
    attempts = 0
    while gem.price < target and attempts < MAX_PUMP_ATTEMPTS:
        prev_frozen = gem.freeze.state == FreezeState.FROZEN
        fill = demo.buy(trader_a, gem.coin_id, 200)
        stp.on_trade(fill, gem, was_frozen=prev_frozen)
        attempts += 1
    print(stp.tail(3))

    print_section("trader-b buy rejected (freeze)")
    try:
        demo.buy(trader_b, gem.coin_id, 5_000)
    except OrderError as e:
        stp.on_error("FREEZE_REJECT", str(e))
    print(stp.tail(1))

    print_section("post-freeze order")
    pfo_target = gem.freeze.ceiling * 1.05
    order = demo.place_post_freeze_order(trader_b, gem.coin_id, "buy", pfo_target, 500)
    stp.on_pfo_place(order, gem)
    print(stp.tail(2))

    print_section("cooldown elapses")
    clock.advance(11.0)
    was_frozen = gem.freeze.state == FreezeState.FROZEN
    demo.tick(gem.coin_id)
    stp.on_tick(gem, was_frozen=was_frozen)
    print(stp.tail(3))

    print_section("fill post-freeze order")
    attempts = 0
    while gem.price < pfo_target and attempts < MAX_PUMP_ATTEMPTS:
        prev = gem.freeze.state == FreezeState.FROZEN
        fill = demo.buy(trader_a, gem.coin_id, 50)
        stp.on_trade(fill, gem, was_frozen=prev)
        was_f = gem.freeze.state == FreezeState.FROZEN
        demo.tick(gem.coin_id)
        stp.on_tick(gem, was_frozen=was_f)
        attempts += 1
    stp.on_pfo_resolved(order, gem)
    print(stp.tail(3))

    print_section("trader-a sells (never frozen)")
    held = demo.wallets.balance(trader_a, gem.coin_id)
    fill = demo.sell(trader_a, gem.coin_id, held * 0.05)
    stp.on_trade(fill, gem, was_frozen=False)
    print(stp.tail(2))

    print_section("launch $DOG + leaderboard snapshot")
    demo.deposit_fiat(founder, 100)
    stp.on_deposit(founder, 100)
    dog = demo.launch_aicoin("DOG", "Doggy Coin", founder, 5_000, 100, 0.05)
    stp.on_launch(dog)
    from chain.stp import encode_leaderboard
    stp.emit(encode_leaderboard(demo.leaderboard(), "MCAP", clock()))
    print(stp.tail(3))

    print_section("mine block")
    block = demo.mine_block()
    stp.on_mine(block)
    print(stp.tail(1))

    print_section(f"stream complete ({len(stp.stream)} lines total)")
    print("# Full tail (last 15 lines):")
    print(stp.tail(15))


if __name__ == "__main__":
    main()
