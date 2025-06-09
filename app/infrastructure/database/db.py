from bcrypt import gensalt, hashpw
from kink import di
from prisma import Prisma

from app.core.config import Configuration
from app.domain.v1.auth.scopes import SCOPE_DESCRIPTIONS


class Database(Prisma):
    @classmethod
    async def connect_db(cls) -> None:
        db = di[Database]

        if not db.is_connected():
            await db.connect()

    @classmethod
    async def disconnect_db(cls) -> None:
        db = di[Database]

        if db.is_connected():
            await db.disconnect()

    @classmethod
    async def init_db(cls) -> None:
        db = di[Database]
        config = di[Configuration]

        await Database.connect_db()

        await cls._ensure_scopes(db)
        await cls._ensure_admin(db, config)

    @classmethod
    async def _ensure_scopes(cls, db: "Database") -> None:
        for scope, description in SCOPE_DESCRIPTIONS.items():
            await db.scope.upsert(
                where={"name": scope},
                data={
                    "create": {"name": scope.value, "description": description},
                    "update": {"description": description},
                },
            )

    @classmethod
    async def _ensure_admin(cls, db: "Database", config: Configuration) -> None:
        db_scope = await db.scope.find_first(where={"name": "admin"})

        await db.client.upsert(
            where={"client_id": "admin"},
            data={
                "create": {
                    "client_id": "admin",
                    "hashed_secret": hashpw(
                        config.admin_password.get_secret_value().encode("utf-8"),
                        gensalt(),
                    ).decode("utf-8"),
                    "scopes": {"connect": [{"id": db_scope.id}]},
                },
                "update": {},
            },
        )
