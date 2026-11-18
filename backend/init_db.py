from app.infrastructure.database import get_engine
from app.infrastructure.models import Base


def init_db():
    # Creates missing tables only; existing tables and rows are left untouched.
    Base.metadata.create_all(bind=get_engine())
    print("Database tables created successfully!")


if __name__ == "__main__":
    init_db()
