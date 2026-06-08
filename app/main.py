"""
FastAPI web server for stir_webserver.

Endpoints:
    POST /login            — Register a user
    POST /send_message     — Send a message to a random user
    GET  /message_history  — Get message history for a user
"""

import os
from contextlib import asynccontextmanager

from beanie import init_beanie
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient

from app.ip_blocking import IPBlockingMiddleware
from app.routes import router
from models.blocked import Blocked
from models.message import Message
from models.user import User


# ---------------------------------------------------------------------------
# Lifespan — connect to MongoDB on startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    connection_string = os.getenv(
        "MONGODB_CONNECTION_STRING",
        "mongodb://localhost:27017",
    )
    database_name = os.getenv(
        "MONGODB_DATABASE_NAME",
        "stir_webserver",
    )
    client = AsyncIOMotorClient(connection_string)
    database = client[database_name]

    await init_beanie(
        database=database,
        document_models=[Message, User, Blocked],
    )
    yield


app = FastAPI(
    title="stir_webserver",
    description="Anonymous messaging server with MongoDB + Beanie.",
    version="0.1.0",
    lifespan=lifespan,
)

# Allow CORS from the frontend domain and local development origins.
# When allow_credentials=True, browsers require a specific origin,
# not "*".  The CORSMiddleware will reflect the request's Origin
# header for any origin in this list.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://stirdotcom.net",
        "https://www.stirdotcom.net",
        "http://localhost:5173",   # Vite dev server
        "http://localhost:3000",   # Alternative dev port
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# IP-based geolocation blocking (enabled via IP_BLOCKING_ENABLED=true)
app.add_middleware(IPBlockingMiddleware)

app.include_router(router, prefix="")
