#!/usr/bin/env python3
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

from app.core.celery_app import celery_app

if __name__ == "__main__":
    celery_app.start(argv=[
        "worker",
        "-B",
        "--loglevel=info",
        "--concurrency=2",
        "-Q", "zeke_default,zeke_processing,zeke_curation,zeke_notifications"
    ])
