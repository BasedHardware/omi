import contextvars

agent_config_context: contextvars.ContextVar[dict | None] = contextvars.ContextVar('agent_config', default=None)
