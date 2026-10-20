"""Additive upgrade from the initial MVP. Existing accounts keep their data."""
from sqlalchemy import inspect, text
from .database import Base

def upgrade(engine):
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(72194318)"))
        Base.metadata.create_all(connection)
        columns = {column["name"] for column in inspect(connection).get_columns("users")}
        for name, size in {"display_name": 80, "bio": 500, "email": 254, "phone": 20, "avatar_url": 255}.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} VARCHAR({size})"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email ON users (email)"))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_phone ON users (phone)"))
        additions = {"player_birth_date": "DATE", "account_status": "VARCHAR(30) NOT NULL DEFAULT 'active'", "guardian_managed": "INTEGER NOT NULL DEFAULT 0"}
        additions.update(role="VARCHAR(20) NOT NULL DEFAULT 'user'", suspended="INTEGER NOT NULL DEFAULT 0")
        additions.update(staff_totp_secret="TEXT",staff_totp_counter="INTEGER NOT NULL DEFAULT -1")
        additions.update(email_verified="INTEGER NOT NULL DEFAULT 0",is_test="INTEGER NOT NULL DEFAULT 0")
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} {definition}"))
        request_columns = {column["name"] for column in inspect(connection).get_columns("legal_requests")}
        if "legal_version" not in request_columns:
            connection.execute(text("ALTER TABLE legal_requests ADD COLUMN legal_version VARCHAR(50)"))
        case_columns = {column["name"] for column in inspect(connection).get_columns("cases")}
        if "moderation_status" not in case_columns:
            connection.execute(text("ALTER TABLE cases ADD COLUMN moderation_status VARCHAR(20) NOT NULL DEFAULT 'published'"))
        token_columns={column["name"] for column in inspect(connection).get_columns("tokens")}
        if "staff_verified" not in token_columns:
            connection.execute(text("ALTER TABLE tokens ADD COLUMN staff_verified INTEGER NOT NULL DEFAULT 0"))
        email_columns={column["name"] for column in inspect(connection).get_columns("email_verifications")}
        if "link_hash" not in email_columns:
            connection.execute(text("ALTER TABLE email_verifications ADD COLUMN link_hash VARCHAR(64)"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_email_link_hash ON email_verifications (link_hash)"))
