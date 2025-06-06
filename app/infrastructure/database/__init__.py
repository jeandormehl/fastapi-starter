from contextlib import asynccontextmanager
from typing import Any

from bcrypt import gensalt, hashpw
from kink import di
from prisma.client import Prisma

from app.core.config import Configuration
from app.domain.v1.auth.scopes import SCOPE_DESCRIPTIONS


class Database(Prisma): ...


async def connect_db() -> None:
    db = di[Database]

    if not db.is_connected():
        await db.connect()


async def disconnect_db() -> None:
    db = di[Database]

    if db.is_connected():
        await db.disconnect()


@asynccontextmanager
async def get_db() -> Any:
    db = di[Database]

    await connect_db()

    try:
        yield db
    finally:
        await disconnect_db()


async def init_db() -> None:
    db = di[Database]
    config = di[Configuration]

    await connect_db()

    for scope, description in SCOPE_DESCRIPTIONS.items():
        # noinspection PyTypeChecker
        db_scope = await db.scope.find_first(where={"name": scope.value})

        # noinspection PyTypeChecker
        if not db_scope:
            db_scope = await db.scope.create(
                data={"name": scope.value, "description": description}
            )

        if db_scope.name == "admin":  # noqa: SIM102
            # noinspection PyTypeChecker
            if not await db.client.find_first(where={"client_id": "administrator"}):
                # noinspection PyTypeChecker
                await db.client.create(
                    data={
                        "client_id": "administrator",
                        "hashed_secret": hashpw(
                            config.admin_password.get_secret_value().encode("utf-8"),
                            gensalt(),
                        ).decode("utf-8"),
                        "scopes": {"connect": [{"id": db_scope.id}]},
                    }
                )
