from fastapi import FastAPI

from llm_gateway.routers import health, openai_compatible

app = FastAPI(title='Omi LLM Gateway')
app.include_router(health.router)
app.include_router(openai_compatible.router)
