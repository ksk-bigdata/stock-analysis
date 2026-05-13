from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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

@app.get("/")
async def root():
    return {"status": "ok", "message": "주식 분석 API 서버"}
