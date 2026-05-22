import os
from fastapi import FastAPI, Request, Response
import modal

# Import routers
from api_routes.auth import router as auth_router
from api_routes.admin import router as admin_router
from api_routes.patients import router as patients_router
from api_routes.gemini import router as gemini_router

# Initialize FastAPI App
web_app = FastAPI(
    title="BioLogic Advanced Medical Reasoning System - Modal Backend",
    description="Decoupled serverless Python backend with zero-trust architecture, vector RAG database routing, and clinical intelligence mining.",
    version="1.0.0"
)

# 🛡️ TITANIUM LAYER: Dynamic Cross-Origin CORS Middleware
# Mirror headers dynamically to support cross-origin HttpOnly cookies and Bearer headers in modern browser sandboxes.
@web_app.middleware("http")
async def cors_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        response = Response()
        origin = request.headers.get("origin")
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, PATCH, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, Cookie, Accept, Range"
            response.headers["Access-Control-Max-Age"] = "86400"
        return response

    response = await call_next(request)
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, PATCH, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, Cookie, Accept, Range"
    return response

# Standard Status Check Routes
@web_app.get("/")
@web_app.get("/api")
@web_app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "BioLogic Clinical Matrix Backend",
        "runtime": "Modal Serverless Python VPS",
        "zero_trust": "active"
    }

# Register all clinical & administrative routing layers
web_app.include_router(auth_router, prefix="/api")
web_app.include_router(admin_router, prefix="/api")
web_app.include_router(patients_router, prefix="/api")
web_app.include_router(gemini_router, prefix="/api")

# ==========================================
# ⚡ MODAL SERVERLESS INTEGRATION (ASGI RUNNER)
# ==========================================
# Define the serverless app in Modal
app = modal.App("biologic-backend")

# Define the container image with all core scientific dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_requirements("requirements.txt")
)

# Export the entire FastAPI app as a serverless ASGI application
@app.function(
    image=image,
    secrets=[modal.Secret.from_name("biologic-secrets")],
    timeout=600  # Generous 10-minute timeout for deep medical literature mining and delta reasoning
)
@modal.asgi_app()
def fastapi_app():
    return web_app
