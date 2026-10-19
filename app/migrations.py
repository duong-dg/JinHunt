"""Additive upgrade from the initial MVP. Existing accounts keep their data."""
from sqlalchemy import inspect, text
from .database import Base

def upgrade(engine):
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(72194318)"))
        Base.metadata.create_all(connection)
        columns = {column["name"] for column in inspect(connection).get_columns("users")}
        for name, size in {"display_name": 80, "bio": 500, "email": 254, "phone": 20}.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} VARCHAR({size})"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email ON users (email)"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_phone ON users (phone)"))
