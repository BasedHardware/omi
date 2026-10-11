import os

from redis.exceptions import AuthenticationError, AuthorizationError, DataError, RedisError, ResponseError
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse, PlainTextResponse

from database import redis_db
from utils.executors import critical_executor, run_blocking
from utils.other.endpoints import get_current_user_uid

router = APIRouter()

DESKTOP_BACKEND_VERSION = "0.1.0"
DESKTOP_BACKEND_SERVICE = "omi-desktop-backend"
CHAT_CONTRACT_VERSION = "1"


def health_response() -> dict[str, str | None]:
    response: dict[str, str | None] = {
        "status": "healthy",
        "service": DESKTOP_BACKEND_SERVICE,
        "version": DESKTOP_BACKEND_VERSION,
        "chat_contract_version": CHAT_CONTRACT_VERSION,
        "runtime_implementation": "python",
    }
    for response_field, environment_name in (
        ("release_tag", "OMI_DESKTOP_RELEASE_TAG"),
        ("release_sha", "OMI_DESKTOP_RELEASE_SHA"),
        ("release_channel", "OMI_DESKTOP_RELEASE_CHANNEL"),
        ("backend_release_sha", "OMI_DESKTOP_BACKEND_RELEASE_SHA"),
        ("backend_release_channel", "OMI_DESKTOP_BACKEND_RELEASE_CHANNEL"),
    ):
        value = os.getenv(environment_name)
        if value is not None:
            response[response_field] = value
    if "backend_release_sha" not in response:
        # Shared Python backend publishes the same /health via this router and
        # stamps OMI_BACKEND_RELEASE_SHA on the Cloud Run revision. Absent env
        # stays null so callers never 500 for missing provenance.
        fallback = os.getenv("OMI_BACKEND_RELEASE_SHA")
        response["backend_release_sha"] = fallback or None
    return response


def redis_readiness_response(configured: bool, probe: bool | Exception | None) -> tuple[int, dict[str, object]]:
    if not configured:
        return status.HTTP_503_SERVICE_UNAVAILABLE, {
            "status": "not_ready",
            "service": DESKTOP_BACKEND_SERVICE,
            "redis": {"status": "not_configured", "failure_class": "not_configured"},
        }
    if probe is True:
        return status.HTTP_200_OK, {
            "status": "ready",
            "service": DESKTOP_BACKEND_SERVICE,
            "redis": {"status": "ready"},
        }
    if probe is False:
        return status.HTTP_503_SERVICE_UNAVAILABLE, {
            "status": "not_ready",
            "service": DESKTOP_BACKEND_SERVICE,
            "redis": {"status": "unexpected_response", "failure_class": "command_data"},
        }
    failure_class = "transport"
    if isinstance(probe, (AuthenticationError, AuthorizationError)):
        failure_class = "auth_config"
    elif isinstance(probe, (ResponseError, DataError)):
        failure_class = "command_data"
    return status.HTTP_503_SERVICE_UNAVAILABLE, {
        "status": "not_ready",
        "service": DESKTOP_BACKEND_SERVICE,
        "redis": {"status": "unavailable", "failure_class": failure_class},
    }


@router.get("/")
@router.get("/health")
def health_check() -> dict[str, str | None]:
    return health_response()


@router.get("/ready")
async def readiness_check() -> JSONResponse:
    configured = bool(os.getenv("REDIS_DB_HOST"))
    probe: bool | Exception | None = None
    if configured:
        try:
            probe = await run_blocking(critical_executor, redis_db.r.ping)
        except RedisError as error:
            probe = error
    status_code, response = redis_readiness_response(configured, probe)
    return JSONResponse(status_code=status_code, content=response)


@router.get("/v1/config/api-keys")
def get_api_keys(_: str = Depends(get_current_user_uid)) -> dict[str, str]:
    return {
        response_field: value
        for response_field, environment_name in (
            ("firebase_api_key", "FIREBASE_API_KEY"),
            ("google_calendar_api_key", "GOOGLE_CALENDAR_API_KEY"),
            ("anthropic_api_key", "DESKTOP_LEGACY_ANTHROPIC_KEY"),
        )
        if (value := os.getenv(environment_name)) is not None
    }


@router.get("/.well-known/apple-developer-domain-association.txt", response_class=PlainTextResponse)
def apple_domain_association() -> str:
    return ""
