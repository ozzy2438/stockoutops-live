"""FastAPI boundary for the minimal M1 intake, review, and audit surface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from stockoutops.config import Settings
from stockoutops.database import Database
from stockoutops.errors import StockoutOpsError
from stockoutops.evidence.manifest import verify_manifest
from stockoutops.evidence.tools import EvidenceTools
from stockoutops.identity import Principal, SimulatedIdentityProvider
from stockoutops.reasoning.deterministic_stub import DeterministicStubAdapter
from stockoutops.repository import Repository
from stockoutops.schemas import IntakeRequest, ReviewRequest
from stockoutops.service import InvestigationService

FORBIDDEN_CLIENT_CONTEXT = frozenset({"actor_id", "tenant_id", "role", "roles"})
TEMPLATES = Jinja2Templates(directory=Path(__file__).parent / "templates")


def _principal(request: Request) -> Principal:
    return request.app.state.identity_provider.resolve(request)


PrincipalDependency = Annotated[Principal, Depends(_principal)]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key")]


def create_app(
    settings: Settings | None = None,
    *,
    service: InvestigationService | None = None,
    identity_provider: SimulatedIdentityProvider | None = None,
    database: Database | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    if service is None:
        database = database or Database(settings.database_url)
        identity_provider = identity_provider or SimulatedIdentityProvider.from_file(
            settings.identities_file, app_env=settings.app_env
        )
        repository = Repository(database)
        manifest_version = verify_manifest(Path("fixtures/v1"))
        service = InvestigationService(
            repository,
            EvidenceTools(repository, manifest_version=manifest_version),
            DeterministicStubAdapter(),
            identity_provider,
        )
    if identity_provider is None:
        identity_provider = service.identity_provider
    if database is None:
        database = service.repository.database

    app = FastAPI(
        title="StockoutOps Live",
        version="0.1.0",
        description=(
            "M1 local simulated human-supervised vertical slice — "
            "implementation candidate pending evidence and assurance."
        ),
    )
    app.state.service = service
    app.state.identity_provider = identity_provider
    app.state.database = database

    @app.exception_handler(StockoutOpsError)
    async def stockoutops_error_handler(_request: Request, exc: StockoutOpsError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.middleware("http")
    async def reject_client_authority(request: Request, call_next):  # type: ignore[no-untyped-def]
        if FORBIDDEN_CLIENT_CONTEXT.intersection(request.query_params):
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "CLIENT_AUTHORITY_FORBIDDEN",
                        "message": "Identity, tenant, and roles are server-derived",
                    }
                },
            )
        return await call_next(request)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        database.health()
        return {"status": "ok", "mode": "local-simulated"}

    @app.post("/v1/investigations")
    def create_investigation(
        request: IntakeRequest,
        principal: PrincipalDependency,
        idempotency_key: IdempotencyKey,
    ) -> JSONResponse:
        run, created = service.intake(principal, request, idempotency_key=idempotency_key)
        body = service.detail(principal, run.run_id)
        body["idempotent_replay"] = not created
        return JSONResponse(
            status_code=201 if created else 200,
            content=jsonable_encoder(body),
        )

    @app.get("/v1/investigations/{run_id}")
    def get_investigation(run_id: UUID, principal: PrincipalDependency) -> dict[str, object]:
        return service.detail(principal, run_id)

    @app.post("/v1/investigations/{run_id}/review")
    def review_investigation(
        run_id: UUID,
        request: ReviewRequest,
        principal: PrincipalDependency,
        idempotency_key: IdempotencyKey,
    ) -> dict[str, object]:
        service.review(
            principal,
            run_id,
            request,
            idempotency_key=idempotency_key,
        )
        return service.detail(principal, run_id)

    @app.get("/v1/investigations/{run_id}/audit")
    def get_audit(run_id: UUID, principal: PrincipalDependency) -> dict[str, object]:
        return service.audit(principal, run_id)

    @app.get("/review", include_in_schema=False)
    def review_page(request: Request):
        return TEMPLATES.TemplateResponse(request=request, name="review.html")

    return app
