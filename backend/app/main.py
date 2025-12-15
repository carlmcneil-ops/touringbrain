from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .api.routes import caravan, touring, towing, briefing

app = FastAPI(
    title="Touring Brain",
    version="0.2.1",
    description="Backend API for Touring Brain – NZ caravan & campervan touring assistant.",
)

# Templates + static (paths are relative to Render "Root Directory" = backend)
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


# ---- Root + UI ----

@app.get("/", include_in_schema=False)
def root():
    # Always land users on the UI
    return RedirectResponse(url="/ui", status_code=302)


@app.get("/ui", response_class=HTMLResponse, tags=["ui"])
async def ui_home(request: Request):
    return templates.TemplateResponse("ui/index.html", {"request": request})


@app.get("/ui/towing", response_class=HTMLResponse, tags=["ui"])
async def ui_towing(request: Request):
    return templates.TemplateResponse("ui/towing.html", {"request": request})


@app.get("/ui/touring", response_class=HTMLResponse, tags=["ui"])
async def ui_touring(request: Request):
    return templates.TemplateResponse("ui/touring.html", {"request": request})


@app.get("/ui/briefing", response_class=HTMLResponse, tags=["ui"])
async def ui_briefing(request: Request):
    return templates.TemplateResponse("ui/briefing.html", {"request": request})


# ---- Health ----

@app.get("/health", tags=["health"])
def health_check():
    return JSONResponse(content={"status": "ok"})


# ---- API routers ----

app.include_router(caravan.router, prefix="/caravan", tags=["caravan"])
app.include_router(touring.router, prefix="/touring", tags=["touring"])
app.include_router(towing.router, prefix="/towing", tags=["towing"])
app.include_router(briefing.router, prefix="/briefing", tags=["briefing"])