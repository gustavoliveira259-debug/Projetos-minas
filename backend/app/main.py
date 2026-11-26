from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .database import init_db
from .routers import arquivos, atividades, equipamentos, powerbi

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="MinePlan Control",
    description="Gerenciamento e acompanhamento do planejamento semanal de lavra — BEMISA.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(atividades.router)
app.include_router(equipamentos.router)
app.include_router(arquivos.router)
app.include_router(powerbi.router)


@app.get("/api/saude", tags=["sistema"])
def saude():
    return {"status": "ok"}


if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
