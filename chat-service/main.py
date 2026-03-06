import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from shared.database import build_mysql_url, make_engine, make_session_factory, Base
from .routes import build_router

load_dotenv()


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


db_url = build_mysql_url(
    host=get_required_env("MYSQLHOST"),
    port=get_required_env("MYSQLPORT"),
    user=get_required_env("MYSQLUSER"),
    password=get_required_env("MYSQLPASSWORD"),
    db=get_required_env("MYSQLDATABASE"),
)

engine = make_engine(db_url)
SessionLocal = make_session_factory(engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables only when app starts, not at import time
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()


app = FastAPI(
    title="Chat Service",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(build_router(SessionLocal), prefix="/chat", tags=["chat"])


@app.get("/health")
def health():
    return {"status": "healthy", "service": "chat-service"}