from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from server.db import init_db
from server.routers import activity, files, settings, sites

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="LTE-R VCS")

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

app.include_router(sites.router)
app.include_router(settings.router)
app.include_router(activity.router)
app.include_router(files.router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")
