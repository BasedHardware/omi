"""Provider-safe reasoning effort binding for notes."""

from typing import Any
from utils.llm.notes_observability import current_run


def bind_notes_effort(model: Any, effort: str) -> Any:
    if effort == 'default':
        return model
    underlying = getattr(model, 'bound', model)
    name = getattr(underlying, 'model_name', None) or getattr(underlying, 'model', None)
    if isinstance(name, str) and not (
        name.rsplit('/', 1)[-1].startswith(('gpt-5.6', 'gpt-6'))
        or type(underlying).__module__ == 'utils.llm.gateway_client'
    ):
        # BYOK can resolve this feature to another provider/model. Keep its own options.
        run = current_run()
        if run is not None:
            run.effort = 'default'
            run.violations.add('effort_unsupported_model')
        from utils.observability.fallback import record_fallback

        record_fallback(
            component='conversation_notes',
            from_mode='episode_effort',
            to_mode='model_default',
            reason='local_heal',
            outcome='degraded',
        )
        return model
    return model.bind(reasoning_effort=effort)
