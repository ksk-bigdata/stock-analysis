from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import asyncio
import os
import socket

# fdr.DataReader 등 네트워크 요청이 무한 대기하는 것 방지
socket.setdefaulttimeout(15)

from api.stocks import router as stocks_router
from api.screener import router as screener_router
from api.alerts import router as alerts_router, check_alerts_loop
from api.auth import router as auth_router

app = FastAPI(title="국내 주식 분석 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/auth", tags=["인증"])
app.include_router(stocks_router, prefix="/api/stocks", tags=["주식"])
app.include_router(screener_router, prefix="/api/screener", tags=["스크리너"])
app.include_router(alerts_router, prefix="/api/alerts", tags=["알림"])

FRONTEND = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/static", StaticFiles(directory=os.path.join(FRONTEND, "static")), name="static")

@app.get("/")
async def index():
    return FileResponse(os.path.join(FRONTEND, "index.html"))

@app.get("/chart")
async def chart():
    return FileResponse(os.path.join(FRONTEND, "chart.html"))

@app.get("/screener")
async def screener():
    return FileResponse(os.path.join(FRONTEND, "screener.html"))

@app.on_event("startup")
async def startup():
    asyncio.create_task(check_alerts_loop())
