from api.hostnames import is_explorer_host


def test_explorer_hosts():
    assert is_explorer_host("explorer.syntrends.com")
    assert is_explorer_host("EXPLORER.syntrends.com:443")
    assert is_explorer_host("www.explorer.syntrends.com")
    assert is_explorer_host("explorer.testnet.syntrends.com")
    assert not is_explorer_host("testnet.syntrends.com")
    assert not is_explorer_host("syntrends.com")
    assert not is_explorer_host(None)
