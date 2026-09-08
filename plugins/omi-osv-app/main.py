"""Standalone, unauthenticated Omi chat tools for public OSV advisories."""

from contextlib import asynccontextmanager
from urllib.parse import quote

import httpx
from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from models import QueryPackageRequest, VulnerabilityRequest
from osv_service import OSVError, bounded_result, fetch_osv, format_advisory, format_query


def create_app(transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    """The optional HTTP transport lets tests exercise real handlers offline."""

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        async with httpx.AsyncClient(
            base_url="https://api.osv.dev",
            timeout=10.0,
            follow_redirects=False,
            headers={"User-Agent": "omi-osv-app/1.0", "Accept": "application/json"},
            transport=transport,
        ) as client:
            application.state.osv_client = client
            yield

    application = FastAPI(title="Omi OSV Advisory Lookup", version="1.0.0", lifespan=lifespan)

    @application.exception_handler(HTTPException)
    async def invalid_body(request: Request, exc: HTTPException):
        if exc.status_code == 400:
            # Body decoding can fail before Pydantic (for example invalid UTF-8).
            return JSONResponse(
                {"error": "Invalid JSON tool request. Send a UTF-8 encoded JSON object."}, status_code=400
            )
        return await http_exception_handler(request, exc)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic errors can contain raw input, including Omi identity fields.
        # Return only a known parameter name, never the input or exception text.
        fields = {"ecosystem", "package_name", "version", "limit", "vulnerability_id"}
        location = next((part for error in exc.errors() for part in error.get("loc", ()) if part in fields), None)
        detail = f"Invalid {location}." if location else "Invalid JSON tool request."
        return JSONResponse(
            {"error": f"{detail} Use the parameter types and limits in the tool manifest."}, status_code=400
        )

    @application.get("/")
    async def home() -> dict[str, str]:
        return {
            "service": "Omi OSV Advisory Lookup",
            "manifest": "/.well-known/omi-tools.json",
            "privacy": "Only public package coordinates or advisory IDs are sent to OSV. Omi identity and location fields are ignored.",
        }

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/.well-known/omi-tools.json")
    async def manifest() -> dict:
        return {
            "tools": [
                {
                    "name": "query_package_vulnerabilities",
                    "description": "Look up OSV advisories for an exact public package version across PyPI, npm, Go, Maven and other supported ecosystems. Returns affected ranges, reported fixed markers and source links. No matches does not prove safety or package existence. Use public package coordinates only.",
                    "endpoint": "/tools/query_package_vulnerabilities",
                    "method": "POST",
                    "parameters": QueryPackageRequest.model_json_schema(),
                    "auth_required": False,
                    "status_message": "Looking up public package advisories...",
                },
                {
                    "name": "get_vulnerability",
                    "description": "Read an OSV advisory by its exact ID (for example GHSA-9hjg-9r4m-mvj7 or PYSEC-2023-74). Returns affected packages, reported fixed markers, withdrawn status and source links. A CVE alias may not be an OSV record ID; use IDs returned by the package lookup.",
                    "endpoint": "/tools/get_vulnerability",
                    "method": "POST",
                    "parameters": VulnerabilityRequest.model_json_schema(),
                    "auth_required": False,
                    "status_message": "Reading the OSV advisory...",
                },
            ]
        }

    @application.post("/tools/query_package_vulnerabilities")
    async def query_package_vulnerabilities(payload: QueryPackageRequest) -> JSONResponse:
        body = {
            "package": {"ecosystem": payload.ecosystem, "name": payload.package_name},
            "version": payload.version,
        }
        try:
            data = await fetch_osv(application.state.osv_client, "/v1/query", body)
            return JSONResponse({"result": format_query(data, payload)})
        except OSVError as exc:
            return JSONResponse({"error": str(exc)}, status_code=exc.status_code)

    @application.post("/tools/get_vulnerability")
    async def get_vulnerability(payload: VulnerabilityRequest) -> JSONResponse:
        try:
            data = await fetch_osv(
                application.state.osv_client, f"/v1/vulns/{quote(payload.vulnerability_id, safe='')}"
            )
            result = format_advisory(data)
            result += "\nFixed markers are source data, not a recommendation across release branches. See the complete advisory before upgrading."
            return JSONResponse({"result": bounded_result(result)})
        except OSVError as exc:
            return JSONResponse({"error": str(exc)}, status_code=exc.status_code)

    return application


app = create_app()
