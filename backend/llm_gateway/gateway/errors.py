from __future__ import annotations

from enum import Enum

from llm_gateway.gateway.schemas import FailureClass


class GatewayErrorCode(str, Enum):
    INVALID_REQUEST = 'invalid_request'
    MODEL_NOT_FOUND = 'model_not_found'
    UNSUPPORTED_MODEL = 'unsupported_model'
    CAPABILITY_NOT_SUPPORTED = 'capability_not_supported'
    INVALID_ROUTE_CONFIG = 'invalid_route_config'
    CREDENTIAL_FAILURE = 'credential_failure'
    PROVIDER_FAILURE = 'provider_failure'


class GatewayError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: GatewayErrorCode,
        failure_class: FailureClass | None = None,
        param: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.failure_class = failure_class
        self.param = param

    def to_error_dict(self) -> dict[str, str | None]:
        return {
            'message': self.message,
            'code': self.code.value,
            'failure_class': self.failure_class.value if self.failure_class is not None else None,
            'param': self.param,
        }


class GatewayInvalidRequestError(GatewayError):
    def __init__(self, message: str, *, param: str | None = None) -> None:
        super().__init__(message, code=GatewayErrorCode.INVALID_REQUEST, param=param)


class GatewayModelNotFoundError(GatewayError):
    def __init__(self, message: str, *, param: str | None = 'model') -> None:
        super().__init__(message, code=GatewayErrorCode.MODEL_NOT_FOUND, param=param)


class GatewayUnsupportedModelError(GatewayError):
    def __init__(self, message: str, *, param: str | None = 'model') -> None:
        super().__init__(message, code=GatewayErrorCode.UNSUPPORTED_MODEL, param=param)


class GatewayCapabilityMismatchError(GatewayError):
    def __init__(self, message: str, *, param: str | None = None) -> None:
        super().__init__(
            message,
            code=GatewayErrorCode.CAPABILITY_NOT_SUPPORTED,
            failure_class=FailureClass.CAPABILITY_MISMATCH,
            param=param,
        )


class GatewayInvalidRouteConfigError(GatewayError):
    def __init__(self, message: str, *, param: str | None = None) -> None:
        super().__init__(
            message,
            code=GatewayErrorCode.INVALID_ROUTE_CONFIG,
            failure_class=FailureClass.INVALID_CONFIG,
            param=param,
        )


class GatewayCredentialFailureError(GatewayError):
    def __init__(self, message: str, *, failure_class: FailureClass, param: str | None = None) -> None:
        super().__init__(
            message,
            code=GatewayErrorCode.CREDENTIAL_FAILURE,
            failure_class=failure_class,
            param=param,
        )


class GatewayProviderFailureError(GatewayError):
    def __init__(self, message: str, *, failure_class: FailureClass, param: str | None = None) -> None:
        super().__init__(
            message,
            code=GatewayErrorCode.PROVIDER_FAILURE,
            failure_class=failure_class,
            param=param,
        )
