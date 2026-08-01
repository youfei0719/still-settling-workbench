import os
import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)
load_dotenv(ROOT / ".env.workbench.local", override=False)

sys.path.insert(0, "backend")
# The open-source workbench starts with an isolated empty library. Existing
# databases are only used when an operator explicitly enables persistence.
os.environ.setdefault("WORKBENCH_DB_MODE", "off")

from app.api.routes.script_workbench import router  # noqa: E402


app = FastAPI(title="依旧沉淀验证服务")
frontend_port = os.getenv("WORKBENCH_FRONTEND_PORT", "5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{frontend_port}",
        f"http://127.0.0.1:{frontend_port}",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api/v1")


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.getenv("WORKBENCH_API_HOST", "127.0.0.1"),
        port=int(os.getenv("WORKBENCH_API_PORT", "8000")),
    )
