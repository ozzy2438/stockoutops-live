"""Environment configuration with local-only simulated identity enforcement."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from stockoutops.errors import ConfigurationError


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_url: str
    identity_provider: str
    identities_file: Path
    reasoning_provider: str

    @classmethod
    def from_env(cls) -> Settings:
        settings = cls(
            app_env=os.getenv("APP_ENV", "local"),
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql://stockoutops_app:app-local-only@localhost:5432/stockoutops",
            ),
            identity_provider=os.getenv("IDENTITY_PROVIDER", "simulated"),
            identities_file=Path(os.getenv("SIMULATED_IDENTITIES_FILE", ".local/identities.json")),
            reasoning_provider=os.getenv("REASONING_PROVIDER", "stub"),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.identity_provider == "simulated" and self.app_env != "local":
            raise ConfigurationError(
                "SimulatedIdentityProvider is forbidden when APP_ENV is not local"
            )
        if self.identity_provider != "simulated":
            raise ConfigurationError("M1 implements only the local simulated identity provider")
        if self.reasoning_provider != "stub":
            raise ConfigurationError(
                "The M1 application factory permits only the deterministic stub; "
                "the OpenAI adapter requires explicit construction for an authorised smoke"
            )
