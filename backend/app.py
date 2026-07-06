"""Professional backend entrypoint for Titan Nova.

The current production runtime still lives in ../flask_app.py. This wrapper lets
future deployments move toward a clean backend/ layout without breaking the
existing two-file runtime.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask_app import app  # noqa: E402


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
