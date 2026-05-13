from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio

from api.stocks import router as stocks_router
from api.screener import router as screener_router
from api.alerts import router as alerts_router, check_alerts_loop

app = FastAPI(title="국내 주식 분석 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stocks_router, prefix="/api/stocks", tags=["주식"])
app.include_router(screener_router, prefix="/api/screener", tags=["스크리너"])
app.include_router(alerts_router, prefix="/api/alerts", tags=["알림"])

@app.on_event("startup")
async def startup():
    asyncio.create_task(check_alerts_loop())

@app.get("/")
async def root():
    return {"status": "ok", "message": "주식 분석 API 서버"}
