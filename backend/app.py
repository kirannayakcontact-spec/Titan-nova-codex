"""Compatibility entrypoint for the clean Andres Berlin era.

The legacy root Flask monolith has been moved to ``legacy-backup/``. New active
backend development lives in ``andres-berlin/backend``.
"""

from flask import Flask, jsonify

app = Flask(__name__)


@app.get("/health")
def health():
    """Return a small compatibility health response."""

    return {"status": "ok", "activeProject": "andres-berlin"}


@app.get("/")
def index():
    """Point callers to the new project folder."""

    return jsonify({"message": "Use andres-berlin as the active clean project."})


__all__ = ["app"]


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
