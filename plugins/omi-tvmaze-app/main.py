"""FastAPI adapter for the TVMaze Omi chat tools."""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

import service

app = FastAPI(title="Omi TVMaze Integration", version="1.0.0")


@app.get("/", response_class=HTMLResponse)
def root():
    return (
        "<h1>TVMaze × Omi</h1><p>Find a TV show and its next announced episode. No sign-in required.</p>"
        '<p>Data from <a href="https://www.tvmaze.com">TVMaze</a>, licensed under '
        '<a href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA</a>.</p>'
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/.well-known/omi-tools.json")
def manifest():
    return {"tools": service.TOOLS}


# Synchronous handlers run in FastAPI's thread pool, keeping blocking urllib
# requests off the event loop. Each provider connection is closed after use.
@app.post("/tools/search_tv_shows")
def search_tv_shows(payload: dict):
    return service.search_tv_shows(payload)


@app.post("/tools/get_tv_show")
def get_tv_show(payload: dict):
    return service.get_tv_show(payload)
