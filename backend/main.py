from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, constr
import asyncpg
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Flappy-RO API")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://flappy:flappypass@postgres-service:5432/flappydb")

pool: asyncpg.Pool = None


@app.on_event("startup")
async def startup():
    global pool
    import asyncio
    for attempt in range(10):
        try:
            pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
            async with pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS scores (
                        id SERIAL PRIMARY KEY,
                        player_name VARCHAR(50) NOT NULL,
                        score INTEGER NOT NULL,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """)
            logger.info("Database connected and table ready.")
            break
        except Exception as e:
            logger.warning(f"DB connect attempt {attempt+1}/10 failed: {e}")
            await asyncio.sleep(3)
    else:
        logger.error("Could not connect to database after 10 attempts.")


@app.on_event("shutdown")
async def shutdown():
    if pool:
        await pool.close()


class ScoreIn(BaseModel):
    player_name: str
    score: int


class ScoreOut(BaseModel):
    id: int
    player_name: str
    score: int


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/scores", response_model=list[ScoreOut])
async def get_scores(limit: int = 10):
    if not pool:
        raise HTTPException(status_code=503, detail="Database not available")
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, player_name, score FROM scores ORDER BY score DESC LIMIT $1",
            min(limit, 100)
        )
    return [dict(r) for r in rows]


@app.post("/scores", response_model=ScoreOut, status_code=201)
async def post_score(data: ScoreIn):
    if not pool:
        raise HTTPException(status_code=503, detail="Database not available")
    if data.score < 0 or data.score > 9999:
        raise HTTPException(status_code=400, detail="Invalid score")
    name = data.player_name.strip()[:50] or "ANONIM"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO scores (player_name, score) VALUES ($1, $2) RETURNING id, player_name, score",
            name, data.score
        )
    return dict(row)


# Serve frontend
app.mount("/", StaticFiles(directory="/app/frontend", html=True), name="frontend")
