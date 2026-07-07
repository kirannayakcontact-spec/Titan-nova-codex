"""WhatsApp bridge routes."""

from flask import jsonify

from backend.services.whatsapp_gateway import gateway_status


def register(app):
    @app.get("/api/whatsapp/status")
    def whatsapp_status():
        return jsonify(gateway_status())
