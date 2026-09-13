"""FastAPI adapter for the public iNaturalist chat tools."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from inaturalist import INaturalistTools, manifest


@asynccontextmanager
async def lifespan(app):
    app.state.tools = INaturalistTools()
    yield


app = FastAPI(title="Omi iNaturalist Wildlife Lookup", version="1.0.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    return JSONResponse({"error": "Tool input must be a valid JSON object."}, status_code=200)


@app.get("/")
async def home():
    return {"name": "iNaturalist Wildlife Lookup", "manifest": "/.well-known/omi-tools.json"}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "omi-inaturalist-app"}


@app.get("/.well-known/omi-tools.json")
async def tools_manifest():
    return manifest()


@app.post("/tools/search_inaturalist_taxa")
async def search_taxa(payload: dict):
    return await app.state.tools.run("search_inaturalist_taxa", payload)


@app.post("/tools/get_inaturalist_taxon")
async def get_taxon(payload: dict):
    return await app.state.tools.run("get_inaturalist_taxon", payload)


@app.post("/tools/search_inaturalist_places")
async def search_places(payload: dict):
    return await app.state.tools.run("search_inaturalist_places", payload)


@app.post("/tools/get_inaturalist_observed_taxa")
async def observed_taxa(payload: dict):
    return await app.state.tools.run("get_inaturalist_observed_taxa", payload)
