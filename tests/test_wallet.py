import pytest

from chain.wallet import InsufficientBalance, WalletRegistry


def test_wallet_created_once_and_stable():
    w = WalletRegistry()
    addr1 = w.get_or_create_wallet("agent1", "coinA")
    addr2 = w.get_or_create_wallet("agent1", "coinA")
    assert addr1 == addr2


def test_wallet_unique_per_agent_and_coin():
    w = WalletRegistry()
    a = w.get_or_create_wallet("agent1", "coinA")
    b = w.get_or_create_wallet("agent1", "coinB")
    c = w.get_or_create_wallet("agent2", "coinA")
    assert len({a, b, c}) == 3


def test_no_wallet_until_first_use():
    w = WalletRegistry()
    assert w.wallet_for("agent1", "coinA") is None
    assert w.balance("agent1", "coinA") == 0.0


def test_credit_debit_coin_balance():
    w = WalletRegistry()
    w.credit("agent1", "coinA", 100.0)
    assert w.balance("agent1", "coinA") == 100.0
    w.debit("agent1", "coinA", 40.0)
    assert w.balance("agent1", "coinA") == 60.0


def test_debit_more_than_balance_raises():
    w = WalletRegistry()
    w.credit("agent1", "coinA", 10.0)
    with pytest.raises(InsufficientBalance):
        w.debit("agent1", "coinA", 20.0)


def test_debit_without_wallet_raises():
    w = WalletRegistry()
    with pytest.raises(InsufficientBalance):
        w.debit("agent1", "coinA", 1.0)


def test_fiat_deposit_and_debit():
    w = WalletRegistry()
    w.deposit_fiat("agent1", 500.0)
    assert w.fiat_balance("agent1") == 500.0
    w.debit_fiat("agent1", 200.0)
    assert w.fiat_balance("agent1") == 300.0


def test_debit_fiat_insufficient_raises():
    w = WalletRegistry()
    w.deposit_fiat("agent1", 50.0)
    with pytest.raises(InsufficientBalance):
        w.debit_fiat("agent1", 100.0)
