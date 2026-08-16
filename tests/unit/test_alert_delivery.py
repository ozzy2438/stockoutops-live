from __future__ import annotations

import json
import os
import socket
import time
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from stockoutops.alerting.contracts import AlertCorrelation, AlertEvaluation
from stockoutops.alerting.delivery import should_notify
from stockoutops.alerting.delivery_settings import (
    AlertDeliverySettings,
    parse_enabled_flag,
    validate_webhook_url,
)
from stockoutops.alerting.enqueue import WebhookOutboxEnqueuer, build_delivery_enqueuer
from stockoutops.alerting.outbox import backoff_delay_seconds, delivery_idempotency_key
from stockoutops.alerting.sink import DisabledAlertSink, build_alert_sink
from stockoutops.alerting.webhook import (
    WebhookTransport,
    classify_transport_error,
    webhook_payload,
)
from stockoutops.alerting.worker import (
    WorkerRunResult,
    build_worker,
    classify_exception,
    classify_response,
)
from stockoutops.errors import ConfigurationError
from stockoutops.identity import Principal
from tests.webhook_receiver import RecordingWebhookServer

SECRET_TOKEN = "super-secret-webhook-token-value"


def _principal() -> Principal:
    return Principal("alert-test-operator", "t_alpha", frozenset({"operator"}))


def _evaluation(**overrides: Any) -> AlertEvaluation:
    payload = {
        "evaluation_id": 1,
        "alert_fingerprint": "a" * 64,
        "policy_id": "shadow-escalation-disagreement-rate",
        "policy_version": "m2-alert-policy-v1",
        "metric_name": "escalation_disagreement_rate",
        "tenant_id": "t_alpha",
        "correlation": AlertCorrelation(tenant_id="t_alpha"),
        "severity": "SEV2",
        "state": "FIRING",
        "previous_state": None,
        "transition": "FIRED",
        "measurement_status": "EVALUATED",
        "threshold_classification": "ENGINEERING TEST THRESHOLD",
        "threshold_value": 0.20,
        "comparator": ">",
        "observed_value": 0.3,
        "window": "one tenant-scoped shadow report batch",
        "window_id": "window-001",
        "evidence_label": "SIMULATED",
        "source_report_sha256": "b" * 64,
        "payload_hash": "c" * 64,
        "idempotency_key": "key-1",
        "live_slo_evidence_eligible": False,
        "execute": False,
        "external_alert_delivery_count": 0,
        "actor_id": "alert-test-operator",
        "evaluated_at": datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
        "idempotent_replay": False,
    }
    payload.update(overrides)
    return AlertEvaluation(**payload)


def _settings(url: str, **overrides: Any) -> AlertDeliverySettings:
    payload = {
        "enabled": True,
        "webhook_url": url,
        "timeout_seconds": 1.0,
        "max_attempts": 2,
        "token": None,
    }
    payload.update(overrides)
    return AlertDeliverySettings(**payload)


def test_delivery_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "STOCKOUTOPS_ALERT_WEBHOOK_ENABLED",
        "STOCKOUTOPS_ALERT_WEBHOOK_URL",
        "STOCKOUTOPS_ALERT_WEBHOOK_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = AlertDeliverySettings.from_env()
    assert settings.enabled is False
    assert parse_enabled_flag(None) is False
    assert parse_enabled_flag("false") is False
    assert parse_enabled_flag("true") is True
    assert isinstance(build_alert_sink(), DisabledAlertSink)
    assert build_delivery_enqueuer(settings) is None


def test_enabled_without_url_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKOUTOPS_ALERT_WEBHOOK_ENABLED", "true")
    monkeypatch.delenv("STOCKOUTOPS_ALERT_WEBHOOK_URL", raising=False)
    with pytest.raises(ConfigurationError, match="WEBHOOK_URL is required"):
        AlertDeliverySettings.from_env()


def test_webhook_url_validation_is_https_except_loopback() -> None:
    assert validate_webhook_url("http://127.0.0.1:8080/alerts").startswith("http://127.0.0.1")
    assert validate_webhook_url("https://alerts.example.test/hook").startswith("https://")
    with pytest.raises(ConfigurationError, match="must use HTTPS except for loopback"):
        validate_webhook_url("http://alerts.example.test/hook")
    with pytest.raises(ConfigurationError, match="must not contain credentials"):
        validate_webhook_url("https://user:pass@alerts.example.test/hook")
    with pytest.raises(ConfigurationError, match="must use http or https"):
        validate_webhook_url("ftp://127.0.0.1/alerts")


def test_disabled_sink_performs_no_network_io() -> None:
    with RecordingWebhookServer() as receiver:
        DisabledAlertSink().deliver(_principal(), _evaluation())
        assert receiver.requests == []


def test_payload_is_labelled_simulated_and_omits_secrets() -> None:
    payload = webhook_payload(_evaluation())
    dumped = json.dumps(payload)
    assert payload["evidence_label"] == "SIMULATED"
    assert payload["live_slo_evidence_eligible"] is False
    assert payload["execute"] is False
    assert "token" not in payload
    assert "Authorization" not in dumped
    assert SECRET_TOKEN not in dumped
    assert should_notify(_evaluation()) is True
    assert should_notify(_evaluation(transition="STILL_FIRING", state="FIRING")) is False
    assert should_notify(_evaluation(idempotent_replay=True)) is False


def test_transport_posts_once_with_the_stable_idempotency_key() -> None:
    with RecordingWebhookServer() as receiver:
        transport = WebhookTransport(_settings(receiver.url))
        status = transport.post(
            webhook_payload(_evaluation()),
            idempotency_key=delivery_idempotency_key("t_alpha", 1, "FIRED"),
        )
    assert status == 200
    assert len(receiver.requests) == 1
    request = receiver.requests[0]
    assert request["body"]["transition"] == "FIRED"
    assert request["body"]["evidence_label"] == "SIMULATED"
    assert request["idempotency_key"] == "t_alpha:1:FIRED"


def test_idempotency_key_is_deterministic_and_tenant_qualified() -> None:
    first = delivery_idempotency_key("t_alpha", 7, "RESOLVED")
    assert first == delivery_idempotency_key("t_alpha", 7, "RESOLVED")
    assert first != delivery_idempotency_key("t_beta", 7, "RESOLVED")
    assert first != delivery_idempotency_key("t_alpha", 7, "FIRED")
    assert first.startswith("t_alpha:")


def test_transport_never_follows_redirects() -> None:
    transport = WebhookTransport(_settings("https://alerts.example.test/hook"))
    assert transport.settings.webhook_url == "https://alerts.example.test/hook"
    # follow_redirects is pinned False in WebhookTransport.post; assert the
    # source contract rather than contacting a real redirecting host.
    import inspect

    assert "follow_redirects=False" in inspect.getsource(WebhookTransport.post)


def test_response_classification_separates_retryable_from_permanent() -> None:
    assert classify_response(200).outcome == "DELIVERED"
    assert classify_response(204).outcome == "DELIVERED"

    server_error = classify_response(503)
    assert server_error.outcome == "RETRYABLE_FAILURE"
    assert server_error.retryable is True
    assert server_error.error_class == "http_503"

    client_error = classify_response(400)
    assert client_error.outcome == "PERMANENT_FAILURE"
    assert client_error.retryable is False


def test_timeout_is_classified_ambiguous_not_failed() -> None:
    """A timeout may have reached the receiver; it must never suppress redelivery."""

    decision = classify_exception(httpx.ReadTimeout("timed out"))
    assert decision.outcome == "AMBIGUOUS"
    assert decision.retryable is True
    assert decision.http_status is None
    assert decision.error_class == "timeout"


def test_connection_error_is_retryable_and_unambiguous() -> None:
    decision = classify_exception(httpx.ConnectError("refused"))
    assert decision.outcome == "RETRYABLE_FAILURE"
    assert decision.retryable is True
    assert decision.error_class == "connection_error"


def test_unreachable_receiver_raises_a_bounded_connection_error() -> None:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    transport = WebhookTransport(_settings(f"http://127.0.0.1:{port}/alerts", timeout_seconds=0.2))
    started = time.monotonic()
    with pytest.raises(httpx.HTTPError) as exc_info:
        transport.post({"a": 1}, idempotency_key="k")
    elapsed = time.monotonic() - started
    assert classify_exception(exc_info.value).retryable is True
    assert elapsed < 2.0


def test_timeout_is_bounded_by_the_configured_budget() -> None:
    with RecordingWebhookServer(hang_seconds=1.5) as receiver:
        transport = WebhookTransport(_settings(receiver.url, timeout_seconds=0.2))
        started = time.monotonic()
        with pytest.raises(httpx.HTTPError):
            transport.post({"a": 1}, idempotency_key="k")
        elapsed = time.monotonic() - started
    assert elapsed < 1.4


def test_secret_token_is_sent_but_absent_from_the_payload() -> None:
    with RecordingWebhookServer() as receiver:
        transport = WebhookTransport(_settings(receiver.url, token=SECRET_TOKEN))
        transport.post(webhook_payload(_evaluation()), idempotency_key="k")
        request = receiver.requests[0]
        assert request["authorization"] == f"Bearer {SECRET_TOKEN}"
        assert SECRET_TOKEN not in json.dumps(request["body"])
    assert classify_transport_error(Exception(SECRET_TOKEN)) == "transport_error"
    assert SECRET_TOKEN not in classify_transport_error(Exception(SECRET_TOKEN))


def test_enqueuer_is_none_when_delivery_is_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKOUTOPS_ALERT_WEBHOOK_ENABLED", "false")
    monkeypatch.setenv("STOCKOUTOPS_ALERT_WEBHOOK_URL", "http://127.0.0.1:9/alerts")
    monkeypatch.setenv("STOCKOUTOPS_ALERT_WEBHOOK_TOKEN", SECRET_TOKEN)
    settings = AlertDeliverySettings.from_env()
    assert settings.enabled is False
    assert build_delivery_enqueuer(settings) is None
    assert os.getenv("STOCKOUTOPS_ALERT_WEBHOOK_TOKEN") == SECRET_TOKEN


def test_worker_requires_enabled_settings() -> None:
    disabled = AlertDeliverySettings(enabled=False, webhook_url=None)
    with pytest.raises(ValueError, match="requires enabled delivery settings"):
        build_worker(object(), disabled, worker_id="w")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="requires enabled delivery settings"):
        WebhookOutboxEnqueuer(disabled)


def test_backoff_is_deterministic_bounded_and_capped() -> None:
    assert backoff_delay_seconds(1) == 2.0
    assert backoff_delay_seconds(2) == 4.0
    assert backoff_delay_seconds(3) == 8.0
    assert backoff_delay_seconds(50) == 300.0
    assert backoff_delay_seconds(1) == backoff_delay_seconds(1)


def test_worker_run_result_merges_counters() -> None:
    merged = WorkerRunResult(leased=1, delivered=1).merged(
        WorkerRunResult(leased=2, retried=1, dead_lettered=1, lease_lost=1)
    )
    assert merged == WorkerRunResult(
        leased=3, delivered=1, retried=1, dead_lettered=1, lease_lost=1
    )
