"""Supabase 테이블 초기 설정 스크립트 (최초 1회 실행)"""
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

SQL = """
create table if not exists alerts (
    code        text primary key,
    name        text not null,
    target      numeric not null,
    direction   text not null check (direction in ('above', 'below')),
    set_at      double precision not null
);
"""

def run():
    url = f"{SUPABASE_URL}/rest/v1/rpc/exec_sql"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    # Supabase SQL Editor API (Management API)
    mgmt_url = f"https://api.supabase.com/v1/projects/cctwphvkyhcdeanedttw/database/query"

    print("Supabase 연결 테스트 중...")
    from db.client import get_supabase
    sb = get_supabase()

    # alerts 테이블 존재 여부 확인 (조회 시도)
    try:
        result = sb.table("alerts").select("code").limit(1).execute()
        print("✅ alerts 테이블 이미 존재합니다.")
    except Exception as e:
        print(f"테이블 없음 또는 오류: {e}")
        print("Supabase 대시보드 → SQL Editor에서 아래 SQL을 실행하세요:\n")
        print(SQL)

if __name__ == "__main__":
    run()
