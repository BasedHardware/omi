"""Enrichment consumer route ``POST /v2/enrichment/run`` (contracts (a), (d)); lane 9 fills it.

Mounted once in ``main.py`` by lane 1 after #22388's ``main.py`` edit reaches integration.
"""

from fastapi import APIRouter

router = APIRouter()
