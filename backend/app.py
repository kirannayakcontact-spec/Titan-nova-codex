"""Compatibility entrypoint for the clean Andres Berlin runtime."""

from flask import Flask, jsonify

app = Flask(__name__)


@app.get("/health")
def health():
    """Return a small compatibility health response."""

    return {"status": "ok", "activeProject": "andres-berlin"}


@app.get("/")
def index():
    """Point callers to the active project folder."""

    return jsonify({"message": "Run the active app from andres-berlin."})


__all__ = ["app"]


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
