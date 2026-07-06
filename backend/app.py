"""Backend entrypoint for the Titan Nova Flask application.

The production Flask app currently lives in the repository-root ``flask_app.py``
for backward compatibility with existing deployments. Importing and re-exporting
``app`` here gives new code a stable package path without breaking legacy
commands such as ``python flask_app.py``.
"""

from flask_app import app

__all__ = ["app"]


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
