"""Phase M — published import path smoke."""

from __future__ import annotations


def test_syntrends_package_import_and_version():
    from syntrends import SynTrendsClient, MarketView, __version__

    assert __version__ == "0.1.0"
    assert SynTrendsClient is not None
    assert MarketView is not None
