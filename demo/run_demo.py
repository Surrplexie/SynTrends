"""Scripted, deterministic walkthrough of the SynTrends mini demo blockchain.

Run from the `st/` repo root with:

    python -m demo.run_demo

Uses a ManualClock so the whole "2-4 week" freeze cooldown and 4-day
Post-Freeze Order window are compressed into simulated seconds — the demo
runs instantly and produces the same output every time.
"""

from chain.clock import ManualClock
from chain.engine import SynTrendsDemo
from chain.freeze import FreezeState
from chain.orders import OrderError

MAX_PUMP_ATTEMPTS = 300


def line(title: str = "") -> None:
    print("\n" + "=" * 78)
    if title:
        print(title)
        print("=" * 78)


def main() -> None:
    clock = ManualClock(start=1_700_000_000.0)
    demo = SynTrendsDemo(cooldown_seconds=10.0, pfo_timeout_seconds=15.0, seepnews_cooldown_seconds=0.0, clock=clock)

    line("1. Genesis & agent registration")
    founder, trader_a, trader_b = "agent-founder", "agent-trader-a", "agent-trader-b"
    for agent in (founder, trader_a, trader_b):
        demo.register_agent(agent)
        print(f"  registered {agent}")

    demo.deposit_fiat(founder, 1_000)
    demo.deposit_fiat(trader_a, 20_000)
    demo.deposit_fiat(trader_b, 20_000)
    print(f"  founder fiat balance:  ${demo.wallets.fiat_balance(founder):,.2f}")
    print(f"  trader_a fiat balance: ${demo.wallets.fiat_balance(trader_a):,.2f}")

    line("2. Launch $GEM AICoin (10,000 supply, $1,000 pool, 10% pre-own)")
    gem = demo.launch_aicoin(
        ticker="GEM", name="Gemstone Protocol", creator_agent_id=founder,
        total_supply=10_000, invest_fiat=1_000, pre_own_pct=0.10,
    )
    print(f"  coin_id:       {gem.coin_id}")
    print(f"  launch price:  ${gem.launch_price:.6f}")
    print(f"  pool fiat:     ${gem.pool_fiat_reserve:,.2f}   pool coins: {gem.pool_coin_reserve:,.2f}")
    print(f"  founder holds: {gem.creator_coins:,.2f} GEM (worth ${gem.creator_coins * gem.price:,.2f})")

    line("3. Trader A buys in")
    fill = demo.buy(trader_a, gem.coin_id, 100)
    print(f"  trader_a bought {fill.coin_amount:,.2f} GEM for ${fill.fiat_amount:,.2f} "
          f"(fee ${fill.fee_paid:.4f}) -> price now ${gem.price:.6f}")

    line("4. Pump the price toward the +1024% freeze ceiling")
    target = gem.launch_price * 11.24
    print(f"  target freeze price: ${target:.6f}")
    attempts = 0
    while gem.price < target and attempts < MAX_PUMP_ATTEMPTS:
        demo.buy(trader_a, gem.coin_id, 200)
        attempts += 1
    print(f"  price after {attempts} buys: ${gem.price:.6f}")
    print(f"  freeze state: {gem.freeze.state.value}")
    if gem.freeze.state == FreezeState.FROZEN:
        print(f"  FROZEN at ceiling ${gem.freeze.ceiling:.6f} for {gem.freeze.cooldown_seconds:.0f}s")

    line("5. Trader B tries to buy above the ceiling (should be rejected)")
    try:
        demo.buy(trader_b, gem.coin_id, 5_000)
        print("  unexpected: buy succeeded")
    except OrderError as e:
        print(f"  correctly rejected: {e}")

    line("6. Trader B places a Post-Freeze Order instead")
    pfo_target = gem.freeze.ceiling * 1.05
    order = demo.place_post_freeze_order(trader_b, gem.coin_id, "buy", pfo_target, 500)
    print(f"  order {order.order_id[:8]} queued: buy $500 of GEM once price reaches ${pfo_target:.6f}")

    line("7. Cooldown elapses - freeze lifts")
    clock.advance(11.0)
    demo.tick(gem.coin_id)
    print(f"  freeze state now: {gem.freeze.state.value}")

    line("8. Push the price up to fill the Post-Freeze Order")
    attempts = 0
    while gem.price < pfo_target and attempts < MAX_PUMP_ATTEMPTS:
        demo.buy(trader_a, gem.coin_id, 50)
        demo.tick(gem.coin_id)
        attempts += 1
    demo.tick(gem.coin_id)
    print(f"  price now ${gem.price:.6f} after {attempts} more buys")
    print(f"  post-freeze order status: {order.status} (filled_amount={order.filled_amount})")

    line("9. Trader A sells some GEM back (selling is never frozen)")
    held = demo.wallets.balance(trader_a, gem.coin_id)
    fill = demo.sell(trader_a, gem.coin_id, held * 0.05)
    print(f"  sold {fill.coin_amount:,.2f} GEM for ${fill.fiat_amount:,.2f} -> price now ${gem.price:.6f}")

    line("10. Launch a second, smaller AICoin for the leaderboard")
    demo.deposit_fiat(founder, 100)
    dog = demo.launch_aicoin("DOG", "Doggy Coin", founder, 5_000, 100, 0.05)
    print(f"  $DOG launched at ${dog.launch_price:.6f}, mcap ${dog.market_cap:,.2f}")

    line("11. Leaderboard by market cap")
    for coin in demo.leaderboard(by="market_cap"):
        print(f"  ${coin.ticker:6s} mcap=${coin.market_cap:>12,.2f}  price=${coin.price:.6f}")

    line("12. Seepnews feed (most recent first)")
    for post in demo.seepnews.feed(limit=20):
        who = post.agent_id if post.agent_id else "system"
        print(f"  [{post.category:9s}] ({who:16s}) {post.body}")

    line("13. Mine everything into the blockchain")
    block = demo.mine_block()
    print(f"  mined block #{block.index} with {len(block.transactions)} txs, hash={block.hash[:20]}...")
    print(f"  chain length: {len(demo.chain.chain)} blocks, valid={demo.chain.is_valid()}")

    line("14. Tamper detection check")
    demo.chain.chain[1].transactions[0].payload["amount"] = 999_999_999
    print(f"  chain valid after tampering with block 1's first tx: {demo.chain.is_valid()}")

    line("Demo complete")


if __name__ == "__main__":
    main()
