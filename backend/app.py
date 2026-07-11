"""Compatibility health app for the root Titan Nova runtime.

Production currently starts from the repository root with ``python flask_app.py``
and ``node Gateway.js``. The ``andres-berlin`` folder remains a future modular
rebuild target until a documented migration promotes it.
"""

from flask import Flask, jsonify

app = Flask(__name__)


@app.get("/health")
def health():
    """Return a small compatibility health response."""

    return {"status": "ok", "activeRuntime": "root-legacy", "migrationTarget": "andres-berlin"}


@app.get("/")
def index():
    """Point callers to the new project folder."""

    return jsonify({"message": "Production uses root flask_app.py and Gateway.js. andres-berlin is the future modular rebuild target."})


__all__ = ["app"]


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
