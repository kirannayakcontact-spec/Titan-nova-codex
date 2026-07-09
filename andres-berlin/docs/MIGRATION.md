# Migration Plan

1. Keep the legacy Titan Nova repo stable.
2. Copy only one feature at a time into Andres Berlin.
3. Move business logic into `backend/services/` first.
4. Keep Flask route files thin.
5. Keep Node route files thin and move WhatsApp/runtime logic into focused modules.
6. Add tests after each copied feature before copying the next one.
