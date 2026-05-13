import os
import secrets
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

_valid_tokens: set[str] = set()


class LoginRequest(BaseModel):
    password: str


@router.post("/login")
async def login(req: LoginRequest):
    password = os.getenv("SITE_PASSWORD", "")
    if not password or req.password != password:
        raise HTTPException(status_code=401, detail="비밀번호가 틀렸습니다")
    token = secrets.token_hex(32)
    _valid_tokens.add(token)
    return {"token": token}


@router.get("/verify")
async def verify(token: str):
    if token not in _valid_tokens:
        raise HTTPException(status_code=401, detail="인증 필요")
    return {"ok": True}
