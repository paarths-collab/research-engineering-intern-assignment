import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from perspective.routers.perspective_router import router

app = FastAPI(title="Perspective Simulator API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

@app.get("/")
async def root():
    return {"message": "Perspective Simulator API"}
