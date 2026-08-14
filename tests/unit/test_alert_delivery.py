from __future__ import annotations

import json
import os
import socket
import time
from datetime import UTC, datetime
from typing import Any

import pytest

from stockoutops.alerting.contracts import AlertCorrelation, AlertEvaluation
from stockoutops.alerting.delivery import should_notify
from stockoutops.alerting.delivery_settings import (
    AlertDeliverySettings,
    parse_enabled_flag,
    validate_webhook_url,
)
from stockoutops.alerting.sink import DisabledAlertSink, build_alert_sink
from stockoutops.alerting.webhook import (
    HttpsWebhookSink,
    classify_transport_error,
    webhook_payload,
)
from stockoutops.database import Database
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


class MemoryDeliveryRepository:
    def __init__(self, *, claim_result: bool = True) -> None:
        self.claim_result = claim_result
        self.claims: list[dict[str, Any]] = []
        self.completions: list[dict[str, Any]] = []

    def claim(self, principal: Principal, evaluation: AlertEvaluation, **kwargs: Any) -> bool:
        self.claims.append({"principal": principal, "evaluation": evaluation, **kwargs})
        return self.claim_result

    def complete(self, principal: Principal, evaluation: AlertEvaluation, **kwargs: Any) -> None:
        self.completions.append({"principal": principal, "evaluation": evaluation, **kwargs})


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
    sink = build_alert_sink(Database("postgresql://unused"), settings)
    assert isinstance(sink, DisabledAlertSink)


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


def test_enabled_firing_alert_posts_once() -> None:
    repository = MemoryDeliveryRepository()
    with RecordingWebhookServer() as receiver:
        sink = HttpsWebhookSink(repository, _settings(receiver.url))
        sink.deliver(_principal(), _evaluation())
        assert len(receiver.requests) == 1
        request = receiver.requests[0]
        assert request["body"]["transition"] == "FIRED"
        assert request["body"]["evidence_label"] == "SIMULATED"
        assert request["idempotency_key"] == "t_alpha:1:FIRED"
    assert repository.completions[0]["status"] == "DELIVERED"
    assert repository.completions[0]["attempt_count"] == 1


def test_replay_and_non_lifecycle_transitions_do_not_post() -> None:
    repository = MemoryDeliveryRepository()
    with RecordingWebhookServer() as receiver:
        sink = HttpsWebhookSink(repository, _settings(receiver.url))
        sink.deliver(_principal(), _evaluation(idempotent_replay=True))
        sink.deliver(
            _principal(),
            _evaluation(transition="STILL_FIRING", state="FIRING", previous_state="FIRING"),
        )
        sink.deliver(
            _principal(),
            _evaluation(transition="INITIAL_OK", state="OK", observed_value=0.1),
        )
        assert receiver.requests == []
        assert repository.claims == []


def test_lost_claim_prevents_duplicate_http() -> None:
    repository = MemoryDeliveryRepository(claim_result=False)
    with RecordingWebhookServer() as receiver:
        sink = HttpsWebhookSink(repository, _settings(receiver.url))
        sink.deliver(_principal(), _evaluation())
        assert receiver.requests == []
        assert repository.completions == []


def test_timeout_retries_are_bounded() -> None:
    repository = MemoryDeliveryRepository()
    with RecordingWebhookServer(hang_seconds=0.6) as receiver:
        sink = HttpsWebhookSink(
            repository,
            _settings(receiver.url, timeout_seconds=0.2, max_attempts=2),
        )
        started = time.monotonic()
        sink.deliver(_principal(), _evaluation())
        elapsed = time.monotonic() - started
    completion = repository.completions[0]
    assert completion["status"] == "FAILED"
    assert completion["error_class"] == "timeout"
    assert completion["attempt_count"] == 2
    assert elapsed < 1.5


def test_server_error_retries_client_error_does_not() -> None:
    repository = MemoryDeliveryRepository()
    with RecordingWebhookServer(status_sequence=[503, 200]) as receiver:
        sink = HttpsWebhookSink(repository, _settings(receiver.url))
        sink.deliver(_principal(), _evaluation())
        assert [item["body"]["transition"] for item in receiver.requests] == ["FIRED", "FIRED"]
    assert repository.completions[0]["status"] == "DELIVERED"
    assert repository.completions[0]["attempt_count"] == 2

    repository = MemoryDeliveryRepository()
    with RecordingWebhookServer(status=400) as receiver:
        sink = HttpsWebhookSink(repository, _settings(receiver.url))
        sink.deliver(_principal(), _evaluation())
        assert len(receiver.requests) == 1
    assert repository.completions[0]["status"] == "FAILED"
    assert repository.completions[0]["error_class"] == "http_400"
    assert repository.completions[0]["attempt_count"] == 1


def test_unreachable_receiver_is_a_bounded_connection_failure() -> None:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    repository = MemoryDeliveryRepository()
    sink = HttpsWebhookSink(
        repository,
        _settings(f"http://127.0.0.1:{port}/alerts", timeout_seconds=0.2),
    )
    sink.deliver(_principal(), _evaluation())
    completion = repository.completions[0]
    assert completion["status"] == "FAILED"
    assert completion["error_class"] == "connection_error"
    assert completion["attempt_count"] == 2
    dumped = json.dumps(completion, default=str)
    assert SECRET_TOKEN not in dumped


def test_secret_token_is_sent_but_absent_from_payload_and_completion() -> None:
    repository = MemoryDeliveryRepository()
    with RecordingWebhookServer() as receiver:
        sink = HttpsWebhookSink(
            repository,
            _settings(receiver.url, token=SECRET_TOKEN),
        )
        sink.deliver(_principal(), _evaluation())
        request = receiver.requests[0]
        assert request["authorization"] == f"Bearer {SECRET_TOKEN}"
        assert SECRET_TOKEN not in json.dumps(request["body"])
    dumped = json.dumps(repository.completions, default=str)
    assert SECRET_TOKEN not in dumped
    assert classify_transport_error(Exception(SECRET_TOKEN)) == "transport_error"
    assert SECRET_TOKEN not in classify_transport_error(Exception(SECRET_TOKEN))


def test_disabled_factory_ignores_configured_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOCKOUTOPS_ALERT_WEBHOOK_ENABLED", "false")
    monkeypatch.setenv("STOCKOUTOPS_ALERT_WEBHOOK_URL", "http://127.0.0.1:9/alerts")
    monkeypatch.setenv("STOCKOUTOPS_ALERT_WEBHOOK_TOKEN", SECRET_TOKEN)
    settings = AlertDeliverySettings.from_env()
    assert settings.enabled is False
    sink = build_alert_sink(Database("postgresql://unused"), settings)
    with RecordingWebhookServer() as receiver:
        sink.deliver(_principal(), _evaluation())
        assert receiver.requests == []
    assert os.getenv("STOCKOUTOPS_ALERT_WEBHOOK_TOKEN") == SECRET_TOKEN
