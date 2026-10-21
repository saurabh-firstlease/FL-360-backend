import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import ADMIN_TOKEN, CORS_ORIGINS, MEDIA_ROOT
from app.routers import admin, public

if not ADMIN_TOKEN:
    logging.getLogger("uvicorn.error").warning("ADMIN_TOKEN is not set: all /api/admin endpoints will return 401.")


class MediaFiles(StaticFiles):
    """Uploaded files live in random folders and are never rewritten, so they can be cached forever."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


app = FastAPI(title="FL 360 Walkthrough API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(public.router, prefix="/api")
app.include_router(admin.router, prefix="/api/admin")

MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/media", MediaFiles(directory=MEDIA_ROOT), name="media")


@app.get("/")
def root():
    # This server is only the API; the pages live in the Next.js app.
    return {
        "message": "FL 360 Walkthrough API is running. This is the API only, not a website.",
        "admin_ui": f"{CORS_ORIGINS[0]}/admin" if CORS_ORIGINS else None,
        "api_docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
