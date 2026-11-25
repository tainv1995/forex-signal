import pytest
from fastapi import HTTPException

from app.api.webhook import TradingViewAlertPayload, _normalize_symbol, _verify_secret
from app.core.config import Settings
from app.core.timeframes import TRADINGVIEW_INTERVAL_MAP


def _settings(secret: str = "topsecret") -> Settings:
    return Settings(tradingview_webhook_secret=secret)


def test_verify_secret_accepts_matching_token() -> None:
    _verify_secret("topsecret", None, _settings())


def test_verify_secret_accepts_matching_header() -> None:
    _verify_secret(None, "topsecret", _settings())


def test_verify_secret_rejects_wrong_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _verify_secret("wrong", None, _settings())
    assert exc_info.value.status_code == 401


def test_verify_secret_rejects_when_not_configured() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _verify_secret("anything", None, _settings(secret=""))
    assert exc_info.value.status_code == 503


def test_normalize_symbol_strips_exchange_prefix() -> None:
    assert _normalize_symbol("OANDA:XAUUSD", "XAUUSD") == "XAUUSD"
    assert _normalize_symbol("xauusd", "XAUUSD") == "XAUUSD"


def test_normalize_symbol_rejects_mismatch() -> None:
    assert _normalize_symbol("OANDA:EURUSD", "XAUUSD") is None


def test_all_standard_intervals_are_mapped() -> None:
    for interval in ["1", "5", "15", "30", "60", "240", "D"]:
        assert interval in TRADINGVIEW_INTERVAL_MAP


def test_payload_accepts_ticker_and_timenow_aliases() -> None:
    payload = TradingViewAlertPayload.model_validate(
        {
            "ticker": "OANDA:XAUUSD",
            "timeframe": "15",
            "timenow": "2026-08-17T13:45:00Z",
            "open": 2650.1,
            "high": 2651.0,
            "low": 2649.5,
            "close": 2650.8,
            "volume": 120.0,
        }
    )
    assert payload.symbol == "OANDA:XAUUSD"
    assert payload.interval == "15"
    assert payload.time == "2026-08-17T13:45:00Z"
