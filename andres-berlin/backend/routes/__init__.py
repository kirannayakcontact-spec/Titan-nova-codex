"""Route registration for Andres Berlin."""

from backend.routes import admin, dashboard, ledger, markets, payments, wallet, whatsapp, withdrawals


def register_routes(app):
    """Register all route groups."""

    dashboard.register(app)
    admin.register(app)
    wallet.register(app)
    ledger.register(app)
    payments.register(app)
    withdrawals.register(app)
    whatsapp.register(app)
    markets.register(app)
