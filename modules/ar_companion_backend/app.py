from __future__ import annotations

import argparse

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import router


def create_app() -> FastAPI:
    app = FastAPI(title="AR Companion Backend", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )
    app.include_router(router)
    return app


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="AR companion backend server")
    parser.add_argument("-a", "--bind_addr", type=str, default="127.0.0.1")
    parser.add_argument("-p", "--port", type=int, default=9896)
    args = parser.parse_args()
    uvicorn.run("modules.ar_companion_backend.app:app", host=args.bind_addr, port=args.port, reload=False)


if __name__ == "__main__":
    main()

