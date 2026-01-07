from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import router as api_router

WEB_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000", "http://192.168.128.153:3000"]

app = FastAPI(title="AI Resume Tailor API", version="0.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=WEB_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
