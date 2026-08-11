from pathlib import Path

import pytest
from starlette.requests import Request

from stockoutops.config import Settings
from stockoutops.errors import AuthenticationError, ConfigurationError
from stockoutops.identity import Principal, SimulatedIdentityProvider


def _request(token: str | None) -> Request:
    headers = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    return Request({"type": "http", "headers": headers})


def test_simulated_identity_is_server_derived() -> None:
    provider = SimulatedIdentityProvider(
        {"fake-local-token": Principal("operator-a", "t_alpha", frozenset({"operator"}))},
        {"t_alpha": "reviewer-a"},
        app_env="local",
    )
    principal = provider.resolve(_request("fake-local-token"))
    assert principal.actor_id == "operator-a"
    assert principal.tenant_id == "t_alpha"


@pytest.mark.parametrize("token", [None, "", "wrong"])
def test_missing_or_invalid_identity_fails_closed(token: str | None) -> None:
    provider = SimulatedIdentityProvider({}, {"t_alpha": "reviewer-a"}, app_env="local")
    with pytest.raises(AuthenticationError):
        provider.resolve(_request(token))


def test_simulated_identity_refuses_non_local_startup() -> None:
    with pytest.raises(ConfigurationError):
        SimulatedIdentityProvider({}, {}, app_env="production")
    with pytest.raises(ConfigurationError):
        Settings(
            app_env="production",
            database_url="postgresql://invalid",
            identity_provider="simulated",
            identities_file=Path("ignored"),
            reasoning_provider="stub",
        ).validate()
