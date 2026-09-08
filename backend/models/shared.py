from pydantic import BaseModel, Field


class EmptyResponse(BaseModel):
    """200 response with no body. Use for endpoints that return nothing meaningful."""

    pass


class StatusResponse(BaseModel):
    """Canonical ack response for `{'status': str}` endpoints (deletes, mutations, bulk ops).

    Prefer this over hand-built `{'status': 'ok'}` dicts. Domain-specific status
    responses (e.g. `IntegrationNotificationResponse`) may stay in their domain
    module, but generic acks should use this.
    """

    status: str = Field(description='Human-readable status message, e.g. "ok".')
