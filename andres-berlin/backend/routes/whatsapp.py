"""WhatsApp bridge routes."""

from flask import jsonify, request

from backend.services.whatsapp_gateway import gateway_status, send_whatsapp_message


def register(app):
    @app.get("/api/whatsapp/status")
    def whatsapp_status():
        return jsonify(gateway_status())

    @app.post("/api/whatsapp/messages")
    def whatsapp_send_message():
        body = request.get_json(silent=True) or {}
        try:
            return jsonify(send_whatsapp_message(body.get("to", ""), body.get("message", "")))
        except ValueError as exc:
            return jsonify({"status": "error", "error": str(exc)}), 400
