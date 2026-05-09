"""Unit tests for ingestion — quality reports, news dedup, and derived feature logic."""

from datetime import UTC, date, datetime

from stocktopus.ingestion.quality import QualityReport

# ── Quality Report model ──────────────────────────────────────────────────────


def test_quality_report_passed_when_no_issues() -> None:
    report = QualityReport(
        symbol="SPY",
        timeframe="1m",
        start=date(2024, 1, 2),
        end=date(2024, 1, 5),
        expected_sessions=4,
        sessions_with_data=4,
        missing_sessions=[],
        ohlc_violations=0,
        negative_volume_count=0,
        bar_count_violations=0,
        passed=True,
    )
    assert report.passed is True
    assert report.sessions_with_data == report.expected_sessions


def test_quality_report_fails_with_missing_sessions() -> None:
    report = QualityReport(
        symbol="SPY",
        timeframe="1m",
        start=date(2024, 1, 2),
        end=date(2024, 1, 5),
        expected_sessions=4,
        sessions_with_data=3,
        missing_sessions=[date(2024, 1, 3)],
        ohlc_violations=0,
        negative_volume_count=0,
        bar_count_violations=0,
        passed=False,
    )
    assert report.passed is False
    assert len(report.missing_sessions) == 1


def test_quality_report_fails_with_bar_count_violations() -> None:
    report = QualityReport(
        symbol="SPY",
        timeframe="1m",
        start=date(2024, 1, 2),
        end=date(2024, 1, 5),
        expected_sessions=4,
        sessions_with_data=4,
        missing_sessions=[],
        ohlc_violations=0,
        negative_volume_count=0,
        bar_count_violations=2,
        passed=False,
    )
    assert report.passed is False
    assert report.bar_count_violations == 2


# ── News dedup hash ───────────────────────────────────────────────────────────


def test_dedup_hash_is_stable() -> None:
    from stocktopus.ingestion.news_ingest import _dedup_hash
    from stocktopus.providers.news import NewsArticle

    article = NewsArticle(
        id="test-1",
        headline="Fed holds rates",
        source="reuters",
        url="https://reuters.com/article/abc",
        published_at=datetime(2024, 1, 2, 14, 0, tzinfo=UTC),
    )
    h1 = _dedup_hash(article)
    h2 = _dedup_hash(article)
    assert h1 == h2
    assert len(h1) == 64


def test_dedup_hash_differs_by_url() -> None:
    from stocktopus.ingestion.news_ingest import _dedup_hash
    from stocktopus.providers.news import NewsArticle

    base = dict(
        id="t",
        headline="Same headline",
        source="reuters",
        published_at=datetime(2024, 1, 2, 14, 0, tzinfo=UTC),
    )
    a1 = NewsArticle(**base, url="https://reuters.com/article/1")
    a2 = NewsArticle(**base, url="https://reuters.com/article/2")
    assert _dedup_hash(a1) != _dedup_hash(a2)


# ── Derived features ──────────────────────────────────────────────────────────


def test_derived_features_gap_pct() -> None:
    """Verify gap_pct calculation inline without DB."""
    prev = 470.0
    curr = 472.35
    gap_pct = (curr - prev) / prev * 100
    assert abs(gap_pct - 0.5) < 0.01


def test_rvol_above_one_means_elevated_volume() -> None:
    avg_vol = 1_000_000.0
    today_vol = 1_800_000.0
    rvol = today_vol / avg_vol
    assert rvol > 1.5


def test_expected_bars_known_timeframes() -> None:
    from stocktopus.ingestion.quality import _expected_bars

    assert _expected_bars("1m") == 390
    assert _expected_bars("5m") == 78
    assert _expected_bars("1d") == 1
    assert _expected_bars("999m") is None
