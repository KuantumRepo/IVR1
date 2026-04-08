from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.engine.dialer import dialer_engine
    from app.engine.handlers import event_handler
    import asyncio

    # event_handler.start() internally calls esl_manager.start() which
    # launches the Genesis Consumer background task
    asyncio.create_task(event_handler.start())
    asyncio.create_task(dialer_engine.start())
    
    yield
    
    # Shutdown
    dialer_engine.is_running = False

app = FastAPI(
    title="Broadcaster API",
    description="Backend for Voice Broadcasting & Press-1 Campaign System",
    version="1.0.0",
    lifespan=lifespan
)

# CORS config
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For development, restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.v1.sip_gateways import router as gateways_router
from app.api.v1.agents import router as agents_router
from app.api.v1.caller_ids import router as caller_ids_router
from app.api.v1.audio import router as audio_router
from app.api.v1.call_scripts import router as call_scripts_router
from app.api.v1.contacts import router as contacts_router
from app.api.v1.campaigns import router as campaigns_router
from app.api.v1.ws import router as ws_router

app.include_router(gateways_router, prefix="/api/v1")
app.include_router(agents_router, prefix="/api/v1")
app.include_router(caller_ids_router, prefix="/api/v1")
app.include_router(audio_router, prefix="/api/v1")
app.include_router(call_scripts_router, prefix="/api/v1")
app.include_router(contacts_router, prefix="/api/v1")
app.include_router(campaigns_router, prefix="/api/v1")
app.include_router(ws_router)

@app.get("/")
async def root():
    return {"message": "Broadcaster API is running", "status": "ok"}

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "redis": "unchecked", 
        "postgres": "unchecked",
        "freeswitch": "unchecked"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
