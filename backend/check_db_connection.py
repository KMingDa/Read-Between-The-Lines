from sqlalchemy import text

from app.infrastructure.database import get_engine

try:
    with get_engine().connect() as connection:
        result = connection.execute(text("SELECT 1"))
        print("Database connection successful!")
        print("Test result:", result.scalar())
except Exception as error:
    print("Database connection failed.")
    print("Error type:", type(error).__name__)
    print("Error details:", str(getattr(error, "orig", error)))  # config errors have no .orig
