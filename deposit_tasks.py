"""Redis Queue entry points for CPU-heavy deposit OCR work."""

from __future__ import annotations

import base64
import os


def process_deposit_ocr(image_b64: str, fields: dict):
    """Run OCR in a worker process using the canonical Flask view."""
    from flask_app import app

    payload = {**fields, "image_base64": image_b64}
    with app.test_request_context(
        "/api/deposit/ocr-verify",
        method="POST",
        json=payload,
        headers={"X-Titan-OCR-Worker": "1"},
    ):
        response = app.view_functions["deposit_ocr_verify"]()
        flask_response = response[0] if isinstance(response, tuple) else response
        return flask_response.get_json()


def enqueue_deposit_ocr(image_bytes: bytes, fields: dict):
    """Return an RQ job, or None when no production queue is configured."""
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None
    from redis import Redis
    from rq import Queue

    queue = Queue("deposit-ocr", connection=Redis.from_url(redis_url), default_timeout=180)
    return queue.enqueue(
        process_deposit_ocr,
        base64.b64encode(image_bytes).decode("ascii"),
        fields,
        job_timeout=180,
        result_ttl=3600,
        failure_ttl=86400,
    )
