from chain.block import SynTrendsChain


def test_genesis_block_created_and_valid():
    chain = SynTrendsChain()
    assert len(chain.chain) == 1
    assert chain.chain[0].index == 0
    assert chain.is_valid()


def test_mine_block_with_transactions():
    chain = SynTrendsChain()
    chain.add_transaction("test", {"a": 1})
    chain.add_transaction("test", {"b": 2})
    block = chain.mine_block()
    assert block is not None
    assert len(block.transactions) == 2
    assert len(chain.chain) == 2
    assert chain.is_valid()


def test_mine_with_no_pending_returns_none():
    chain = SynTrendsChain()
    assert chain.mine_block() is None


def test_chain_links_via_previous_hash():
    chain = SynTrendsChain()
    chain.add_transaction("t", {})
    b1 = chain.mine_block()
    chain.add_transaction("t", {})
    b2 = chain.mine_block()
    assert b2.previous_hash == b1.hash
    assert b2.index == b1.index + 1


def test_tamper_detected():
    chain = SynTrendsChain()
    chain.add_transaction("test", {"amount": 100})
    chain.mine_block()
    chain.chain[1].transactions[0].payload["amount"] = 999_999
    assert not chain.is_valid()


def test_all_transactions_iterates_every_block():
    chain = SynTrendsChain()
    chain.add_transaction("a", {})
    chain.mine_block()
    chain.add_transaction("b", {})
    chain.add_transaction("c", {})
    chain.mine_block()
    tx_types = [tx.tx_type for _, tx in chain.all_transactions()]
    assert tx_types == ["a", "b", "c"]
