"""Safely add account roles and search-log ownership to an existing database."""

from sqlalchemy import text

from app.database import Base, engine

# Register the application's existing tables; create_all leaves existing data and tables intact.
from app.models import admin, categories, tile, tile_image, inventory, search_log, cart


def migrate():
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text(
            "ALTER TABLE admins ADD COLUMN IF NOT EXISTS role VARCHAR NOT NULL DEFAULT 'admin'"
        ))
        connection.execute(text(
            """
            UPDATE admins
            SET role = 'user'
            WHERE role IS NULL OR role NOT IN ('super_admin', 'admin', 'user')
            """
        ))
        connection.execute(text(
            "ALTER TABLE admins ALTER COLUMN role SET DEFAULT 'user'"
        ))
        connection.execute(text(
            """
            ALTER TABLE admins
            ADD COLUMN IF NOT EXISTS auth_version INTEGER NOT NULL DEFAULT 0
            """
        ))
        connection.execute(text(
            """
            UPDATE admins
            SET role = 'super_admin',
                is_active = TRUE,
                auth_version = auth_version + CASE
                    WHEN role IS DISTINCT FROM 'super_admin'
                         OR is_active IS NOT TRUE THEN 1
                    ELSE 0
                END
            WHERE email = 'iduraje@gmail.com'
            """
        ))
        connection.execute(text(
            "ALTER TABLE search_logs ADD COLUMN IF NOT EXISTS account_id INTEGER"
        ))
        connection.execute(text(
            """
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'fk_search_logs_account_id_admins'
                ) THEN
                    ALTER TABLE search_logs
                    ADD CONSTRAINT fk_search_logs_account_id_admins
                    FOREIGN KEY (account_id) REFERENCES admins(id) ON DELETE SET NULL;
                END IF;
            END $$;
            """
        ))
        connection.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_search_logs_account_id ON search_logs (account_id)"
        ))
        super_admin_exists = connection.execute(text(
            "SELECT EXISTS (SELECT 1 FROM admins WHERE email = 'iduraje@gmail.com')"
        )).scalar()
    if not super_admin_exists:
        print(
            "WARNING: iduraje@gmail.com was not found; no Super Admin was created. "
            "Create/verify that account, then rerun this migration."
        )
    print("Account roles, token revocation, and search ownership migration complete")


if __name__ == "__main__":
    migrate()
