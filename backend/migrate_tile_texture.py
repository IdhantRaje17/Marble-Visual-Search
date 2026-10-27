"""Add the optional, manually entered tile texture field without changing existing values."""
from sqlalchemy import inspect, text

from app.database import engine


def migrate() -> None:
    inspector = inspect(engine)
    if "texture" in {column["name"] for column in inspector.get_columns("tiles")}:
        print("Tile texture column already exists.")
        return

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE tiles ADD COLUMN texture VARCHAR"))
    print("Added nullable tiles.texture column.")


if __name__ == "__main__":
    migrate()
