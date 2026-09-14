from sqlmodel import Session, SQLModel, create_engine

from server.config import DB_PATH, ensure_data_dirs

ensure_data_dirs()

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
