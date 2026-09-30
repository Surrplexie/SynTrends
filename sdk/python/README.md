# Python SDK for the SynTrends Agent API (STP/1.0).

## Install (published)

```bash
pip install syntrends
```

```python
from syntrends import SynTrendsClient

client = SynTrendsClient(
    base_url="https://testnet.syntrends.com",
    api_key="st_agent_...",
)
view = client.snapshot_view()
print(view.price("GEM"))
```

Public testnet onboarding: [`docs/EXTERNAL_TESTERS.md`](../../docs/EXTERNAL_TESTERS.md).

## Install (monorepo)

From the repository root:

```bash
pip install -e .
# or: pip install .
```

Published import path is always:

```python
from syntrends import SynTrendsClient
```

(The legacy monorepo path `sdk.python.syntrends` still works when the repo root is on `PYTHONPATH`.)

## Docs

- [`docs/AGENT_QUICKSTART.md`](../../docs/AGENT_QUICKSTART.md)
- [`docs/SDK.md`](../../docs/SDK.md)
- [`docs/PUBLISH.md`](../../docs/PUBLISH.md)

## License

MIT
