# Public miners (plan)

**Design goal:** anyone can run a node, validate, mine, earn network rewards.

**Now:** mining is in-process `mine_block()` (SHA-3 prefix) when the API records trades/ticks. Fly testnet is **one app process**, not a miner P2P network.

**Do not** point a miner at `https://testnet.syntrends.com` expecting rewards. There is no public mine RPC.

## What you can run today

Local demo loop (does not touch Fly):

```powershell
python -m demo.run_miner --blocks 3
```

## What still has to exist before “public miners”

1. A standalone node that syncs chain state (not only the HTTP snapshot).
2. A gossip / block-announce protocol other operators can run.
3. Reward economics that are not simulated faucet chip.
4. An explicit “miners are open” announcement (see `docs/MISCONCEPTIONS.md`).

Until then, treat public mining as **planned**. Hostname split (`api.` / `owners.` / `explorer.`) does not change this.
