import contextvars

agent_config_context: contextvars.ContextVar[dict] = contextvars.ContextVar('agent_config', default=None)
