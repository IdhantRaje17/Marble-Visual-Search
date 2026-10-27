#!/usr/bin/env python
from pathlib import Path
import subprocess
import sys

BACKEND_DIR = Path(__file__).resolve().parent

subprocess.run(
    [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ],
    cwd=BACKEND_DIR,
    check=True,
)
