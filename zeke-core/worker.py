#!/usr/bin/env python3
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

if __name__ == "__main__":
    from arq import run_worker
    from app.core.jobs import WorkerSettings
    
    run_worker(WorkerSettings)
