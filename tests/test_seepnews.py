import pytest

from chain.clock import ManualClock
from chain.seepnews import Seepnews, SeepnewsError

TAGS = ["trending", "syntrends", "seepnews"]


def test_post_requires_mention():
    sn = Seepnews(clock=ManualClock(0.0))
    with pytest.raises(SeepnewsError):
        sn.post("agent1", "Trade", "did a trade", mentions=[], hashtags=TAGS)


def test_post_requires_valid_category():
    sn = Seepnews(clock=ManualClock(0.0))
    with pytest.raises(SeepnewsError):
        sn.post("agent1", "Random", "hello $GEM", mentions=["GEM"], hashtags=TAGS)


def test_post_requires_three_hashtags():
    sn = Seepnews(clock=ManualClock(0.0))
    with pytest.raises(SeepnewsError):
        sn.post("agent1", "Trade", "hello $GEM", mentions=["GEM"], hashtags=["one", "two"])


def test_rate_limit_enforced_per_agent():
    clock = ManualClock(0.0)
    sn = Seepnews(cooldown_seconds=60.0, clock=clock)
    sn.post("agent1", "Trade", "bought $GEM", mentions=["GEM"], hashtags=TAGS)
    with pytest.raises(SeepnewsError):
        sn.post("agent1", "Trade", "bought more $GEM", mentions=["GEM"], hashtags=TAGS)
    clock.advance(61.0)
    sn.post("agent1", "Trade", "bought again $GEM", mentions=["GEM"], hashtags=TAGS)  # should not raise


def test_rate_limit_is_per_agent_not_global():
    clock = ManualClock(0.0)
    sn = Seepnews(cooldown_seconds=60.0, clock=clock)
    sn.post("agent1", "Trade", "bought $GEM", mentions=["GEM"], hashtags=TAGS)
    sn.post("agent2", "Trade", "bought $GEM too", mentions=["GEM"], hashtags=TAGS)  # different agent, no wait


def test_duplicate_body_suppressed_across_agents():
    clock = ManualClock(0.0)
    sn = Seepnews(cooldown_seconds=60.0, clock=clock)
    body = "Market outlook on $GEM is bullish"
    sn.post("agent1", "Trade", body, mentions=["GEM"], hashtags=TAGS)
    with pytest.raises(SeepnewsError, match="duplicate post body"):
        sn.post("agent2", "Trade", body, mentions=["GEM"], hashtags=TAGS)
    with pytest.raises(SeepnewsError, match="duplicate post body"):
        sn.post("agent2", "Trade", "  MARKET OUTLOOK on $GEM is BULLISH  ", mentions=["GEM"], hashtags=TAGS)


def test_duplicate_body_lock_expires_with_cooldown():
    clock = ManualClock(0.0)
    sn = Seepnews(cooldown_seconds=60.0, clock=clock)
    body = "Same text about $GEM"
    sn.post("agent1", "Trade", body, mentions=["GEM"], hashtags=TAGS)
    clock.advance(61.0)
    sn.post("agent2", "Trade", body, mentions=["GEM"], hashtags=TAGS)


def test_system_posts_bypass_rate_limit():
    clock = ManualClock(0.0)
    sn = Seepnews(clock=clock)
    sn.system_post("N-AICoin", "launched $GEM", mentions=["GEM"])
    sn.system_post("Freezes", "$GEM froze", mentions=["GEM"])
    assert len(sn.feed()) == 2


def test_feed_returns_most_recent_first():
    clock = ManualClock(0.0)
    sn = Seepnews(clock=clock)
    sn.system_post("System", "first", mentions=["GEM"])
    clock.advance(1.0)
    sn.system_post("System", "second", mentions=["GEM"])
    feed = sn.feed()
    assert feed[0].body == "second"
    assert feed[1].body == "first"


def test_hash_verification():
    sn = Seepnews(clock=ManualClock(0.0))
    p = sn.post("agent1", "Trade", "bought $GEM", mentions=["GEM"], hashtags=TAGS)
    h = sn.hash_db[p.post_id]
    assert sn.verify(p.post_id, h)
    assert not sn.verify(p.post_id, "deadbeef")


def test_prune_expired_posts():
    clock = ManualClock(0.0)
    sn = Seepnews(retention_seconds=100.0, clock=clock)
    sn.system_post("System", "old post", mentions=["GEM"])
    clock.advance(200.0)
    removed = sn.prune_expired()
    assert removed == 1
    assert len(sn.feed()) == 0
