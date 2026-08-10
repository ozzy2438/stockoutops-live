"""Create ignored, random local-only identity fixtures without printing tokens."""

from __future__ import annotations

import json
import secrets
from pathlib import Path


def main() -> None:
    destination = Path(".local")
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    specs = (
        ("t_alpha_operator", "operator-alpha", "t_alpha", ["operator"]),
        ("t_alpha_reviewer_primary", "reviewer-alpha-primary", "t_alpha", ["reviewer"]),
        (
            "t_alpha_reviewer_secondary",
            "reviewer-alpha-secondary",
            "t_alpha",
            ["reviewer"],
        ),
        ("t_beta_operator", "operator-beta", "t_beta", ["operator"]),
        ("t_beta_reviewer", "reviewer-beta-primary", "t_beta", ["reviewer"]),
    )
    identities: list[dict[str, object]] = []
    for name, actor_id, tenant_id, roles in specs:
        token_path = destination / f"{name}.token"
        if token_path.exists():
            token = token_path.read_text(encoding="utf-8").strip()
        else:
            token = f"local-only-{secrets.token_urlsafe(24)}"
            token_path.write_text(token, encoding="utf-8")
            token_path.chmod(0o600)
        identities.append(
            {
                "token": token,
                "actor_id": actor_id,
                "tenant_id": tenant_id,
                "roles": roles,
            }
        )
    payload = {
        "identities": identities,
        "reviewer_assignments": {
            "t_alpha": "reviewer-alpha-primary",
            "t_beta": "reviewer-beta-primary",
        },
    }
    fixture = destination / "identities.json"
    fixture.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    fixture.chmod(0o600)
    print("Created ignored local identity fixture; token values were not printed")


if __name__ == "__main__":
    main()
