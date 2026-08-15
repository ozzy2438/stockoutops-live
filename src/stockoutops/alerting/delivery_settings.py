"""Isolated webhook delivery settings. Not part of the M1 application Settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

from stockoutops.errors import ConfigurationError

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
DEFAULT_TIMEOUT_SECONDS = 2.0
DEFAULT_MAX_ATTEMPTS = 2
MAX_TIMEOUT_SECONDS = 5.0
MAX_ATTEMPTS = 2


def parse_enabled_flag(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def destination_host(url: str) -> str:
    host = urlparse(url).hostname
    if host is None or host == "":
        raise ConfigurationError("Alert webhook URL requires a host")
    return host


def validate_webhook_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.username is not None or parsed.password is not None:
        raise ConfigurationError("Alert webhook URL must not contain credentials")
    if parsed.scheme not in {"http", "https"}:
        raise ConfigurationError("Alert webhook URL must use http or https")
    host = parsed.hostname
    if host is None or host == "":
        raise ConfigurationError("Alert webhook URL requires a host")
    is_loopback = host.lower() in LOOPBACK_HOSTS
    if parsed.scheme == "http" and not is_loopback:
        raise ConfigurationError(
            "Alert webhook URL must use HTTPS except for loopback proof receivers"
        )
    if parsed.port == 0:
        raise ConfigurationError("Alert webhook URL port is invalid")
    return url


def _parse_timeout(raw: str | None) -> float:
    if raw is None or raw.strip() == "":
        return DEFAULT_TIMEOUT_SECONDS
    try:
        timeout = float(raw)
    except ValueError as exc:
        raise ConfigurationError(
            "STOCKOUTOPS_ALERT_WEBHOOK_TIMEOUT_SECONDS must be a number"
        ) from exc
    if timeout <= 0 or timeout > MAX_TIMEOUT_SECONDS:
        raise ConfigurationError(
            f"STOCKOUTOPS_ALERT_WEBHOOK_TIMEOUT_SECONDS must be > 0 and <= {MAX_TIMEOUT_SECONDS:g}"
        )
    return timeout


def _parse_max_attempts(raw: str | None) -> int:
    if raw is None or raw.strip() == "":
        return DEFAULT_MAX_ATTEMPTS
    try:
        attempts = int(raw)
    except ValueError as exc:
        raise ConfigurationError(
            "STOCKOUTOPS_ALERT_WEBHOOK_MAX_ATTEMPTS must be an integer"
        ) from exc
    if attempts < 1 or attempts > MAX_ATTEMPTS:
        raise ConfigurationError(
            f"STOCKOUTOPS_ALERT_WEBHOOK_MAX_ATTEMPTS must be between 1 and {MAX_ATTEMPTS}"
        )
    return attempts


@dataclass(frozen=True)
class AlertDeliverySettings:
    enabled: bool
    webhook_url: str | None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    token: str | None = None

    @classmethod
    def from_env(cls) -> AlertDeliverySettings:
        enabled = parse_enabled_flag(os.getenv("STOCKOUTOPS_ALERT_WEBHOOK_ENABLED"))
        raw_url = os.getenv("STOCKOUTOPS_ALERT_WEBHOOK_URL")
        webhook_url = raw_url.strip() if raw_url and raw_url.strip() else None
        token = os.getenv("STOCKOUTOPS_ALERT_WEBHOOK_TOKEN")
        token = token if token else None
        settings = cls(
            enabled=enabled,
            webhook_url=webhook_url,
            timeout_seconds=_parse_timeout(os.getenv("STOCKOUTOPS_ALERT_WEBHOOK_TIMEOUT_SECONDS")),
            max_attempts=_parse_max_attempts(os.getenv("STOCKOUTOPS_ALERT_WEBHOOK_MAX_ATTEMPTS")),
            token=token,
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not self.enabled:
            return
        if self.webhook_url is None:
            raise ConfigurationError(
                "STOCKOUTOPS_ALERT_WEBHOOK_URL is required when webhook delivery is enabled"
            )
        validate_webhook_url(self.webhook_url)
        if self.timeout_seconds <= 0 or self.timeout_seconds > MAX_TIMEOUT_SECONDS:
            raise ConfigurationError("Webhook timeout is outside the allowed bound")
        if self.max_attempts < 1 or self.max_attempts > MAX_ATTEMPTS:
            raise ConfigurationError("Webhook max attempts are outside the allowed bound")
