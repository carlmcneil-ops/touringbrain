from fastapi.responses import RedirectResponse
from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request

from .api.routes import caravan, touring, towing, briefing

app = FastAPI(
    title="Touring Brain",
    version="0.2.1",
    description="Backend API for Touring Brain – NZ caravan & campervan touring assistant.",
)

templates = Jinja2Templates(directory="app/templates")

# ---- Static files (CSS + JS) ----

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/ui")


@app.get("/health", tags=["health"])
def health_check():
    """
    Basic health check endpoint used for monitoring and deployment.
    """
    return JSONResponse(content={"status": "ok"})


# ---- API Routers ----

app.include_router(
    caravan.router,
    prefix="/caravan",
    tags=["caravan"],
)

app.include_router(
    touring.router,
    prefix="/touring",
    tags=["touring"],
)

app.include_router(
    towing.router,
    prefix="/towing",
    tags=["towing"],
)

app.include_router(
    briefing.router,
    prefix="/briefing",
    tags=["briefing"],
)

@app.get("/ui/towing", response_class=HTMLResponse, tags=["ui"])
async def towing_ui(request: Request):
    return templates.TemplateResponse("ui/towing.html", {"request": request})


@app.get("/ui/touring", response_class=HTMLResponse, tags=["ui"])
async def touring_ui(request: Request):
    return templates.TemplateResponse("ui/touring.html", {"request": request})

@app.get("/ui/briefing", tags=["ui"])
async def ui_briefing(request: Request):
    return templates.TemplateResponse("ui/briefing.html", {"request": request})

@app.get("/ui", response_class=HTMLResponse)
async def ui_home(request: Request):
    return templates.TemplateResponse("ui/index.html", {"request": request}) 