<content>
from typing import Any, Dict, Optional

from django.http import HttpRequest, JsonResponse
from ninja import Router
from ninja.errors import HttpError

from apps.personas.models import Persona
from apps.personas.schemas import PersonaMutationResponse, PersonaPartialUpdateSchema

router = Router(tags=["Personas"])


@router.patch("/v1/personas/{persona_id}", response=PersonaMutationResponse)
def partial_update_persona(
    request: HttpRequest, persona_id: int, data: PersonaPartialUpdateSchema
) -> PersonaMutationResponse:
    persona = Persona.objects.get(id=persona_id)

    # Treat explicit nulls as "not sent" for optional fields to prevent 500s
    if data.connected_accounts is None:
        data.connected_accounts = persona.connected_accounts
    if data.username is None:
        data.username = persona.username

    # Apply partial update logic
    update_fields: list[str] = []
    for field, value in data.dict(exclude_unset=True).items():
        setattr(persona, field, value)
        update_fields.append(field)

    persona.save(update_fields=update_fields)
    return PersonaMutationResponse.from_orm(persona)
</content>