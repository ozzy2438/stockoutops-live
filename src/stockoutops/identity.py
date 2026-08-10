"""Server-derived local simulated identity boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fastapi import Request

from stockoutops.errors import AuthenticationError, ConfigurationError


@dataclass(frozen=True)
class Principal:
    actor_id: str
    tenant_id: str
    roles: frozenset[str]

    def has_role(self, role: str) -> bool:
        return role in self.roles


class IdentityProvider(Protocol):
    def resolve(self, request: Request) -> Principal: ...

    def assigned_reviewer(self, tenant_id: str) -> str: ...


class SimulatedIdentityProvider:
    def __init__(
        self,
        token_map: dict[str, Principal],
        reviewer_assignments: dict[str, str],
        *,
        app_env: str,
    ) -> None:
        if app_env != "local":
            raise ConfigurationError("SimulatedIdentityProvider cannot start outside APP_ENV=local")
        self._token_map = dict(token_map)
        self._reviewer_assignments = dict(reviewer_assignments)

    @classmethod
    def from_file(cls, path: Path, *, app_env: str) -> SimulatedIdentityProvider:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(
                f"Unable to load ignored local identity fixture: {path}"
            ) from exc
        identities = payload.get("identities")
        assignments = payload.get("reviewer_assignments")
        if not isinstance(identities, list) or not isinstance(assignments, dict):
            raise ConfigurationError("Invalid local identity fixture structure")
        token_map: dict[str, Principal] = {}
        for item in identities:
            token = item.get("token")
            roles = item.get("roles")
            if not token or not isinstance(roles, list):
                raise ConfigurationError("Invalid identity fixture entry")
            token_map[token] = Principal(
                actor_id=item["actor_id"],
                tenant_id=item["tenant_id"],
                roles=frozenset(roles),
            )
        return cls(token_map, assignments, app_env=app_env)

    def resolve(self, request: Request) -> Principal:
        authorization = request.headers.get("Authorization", "")
        scheme, separator, token = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not token:
            raise AuthenticationError()
        principal = self._token_map.get(token)
        if principal is None:
            raise AuthenticationError()
        return principal

    def assigned_reviewer(self, tenant_id: str) -> str:
        try:
            return self._reviewer_assignments[tenant_id]
        except KeyError as exc:
            raise ConfigurationError(
                f"No server-side reviewer assignment for tenant {tenant_id}"
            ) from exc
