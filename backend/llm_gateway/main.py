from fastapi import FastAPI

from llm_gateway.routers import health

app = FastAPI(title='Omi LLM Gateway')
app.include_router(health.router)
