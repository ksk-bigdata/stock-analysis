from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from api.stocks import router as stocks_router
from api.screener import router as screener_router

app = FastAPI(title="국내 주식 분석 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stocks_router, prefix="/api/stocks", tags=["주식"])
app.include_router(screener_router, prefix="/api/screener", tags=["스크리너"])

frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/static", StaticFiles(directory=os.path.join(frontend_path, "static")), name="static")

@app.get("/", include_in_schema=False)
async def serve_index():
    return FileResponse(os.path.join(frontend_path, "index.html"))

@app.get("/chart", include_in_schema=False)
async def serve_chart():
    return FileResponse(os.path.join(frontend_path, "chart.html"))

@app.get("/screener", include_in_schema=False)
async def serve_screener():
    return FileResponse(os.path.join(frontend_path, "screener.html"))
