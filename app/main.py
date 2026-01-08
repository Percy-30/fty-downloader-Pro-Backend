# app/main.py
import logging
import asyncio
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.limits import limiter

from app.config import settings
from app.routes.download_routes import router as download_router
from app.routes.youtube_routes import router as youtube_router
from app.routes.audio_routes import router as audio_router
from app.routes.cookies_routes import router as cookies_router
from app.routes.combiner_routes import router as combiner_router
from app.routes.facebook_routes import router as facebook_router  # ✅ NUEVO: Facebook routes
from app.services.base_extractor import SnapTubeError
from app.services.youtube_cookie_updater import login_youtube_and_save_cookies
from app.cookies.check_cookies import cookies_are_valid


# ==========================================================
# LOGGING CONFIG
# ==========================================================
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format=settings.LOG_FORMAT
)
logger = logging.getLogger(__name__)

# ==========================================================
# COOKIES MANAGEMENT
# ==========================================================
_last_cookie_update_attempt = None

def ensure_valid_cookies(force: bool = False) -> bool:
    """Verifica y actualiza cookies si es necesario."""
    global _last_cookie_update_attempt

    if not force and _last_cookie_update_attempt and (datetime.now() - _last_cookie_update_attempt).seconds < 60:
        logger.warning("⏳ Último intento de actualización de cookies fue hace menos de 1 min. Saltando...")
        return False

    _last_cookie_update_attempt = datetime.now()

    if force or not cookies_are_valid():
        logger.warning("⚠️ Cookies inválidas o ausentes. Intentando regenerar...")
        try:
            login_youtube_and_save_cookies()
            return cookies_are_valid()
        except Exception as e:
            logger.error(f"💥 Error regenerando cookies: {str(e)}", exc_info=True)
            return False
    return True

# ==========================================================
# APP LIFESPAN
# ==========================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup & Shutdown"""
    logger.info("🚀 FreeDownloaderPro API starting up...")

    # Crear directorios necesarios
    settings.TEMP_DIR.mkdir(exist_ok=True)
    settings.COOKIES_DIR.mkdir(exist_ok=True)
    settings.YOUTUBE_COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Verificar cookies al iniciar
    if not ensure_valid_cookies():
        logger.error("🚨 No se pudieron generar cookies al iniciar. El API puede fallar en peticiones a YouTube.")

    # ✅ DIAGNÓSTICO DE DENO (Requerido para YouTube HD)
    try:
        import subprocess
        deno_version = subprocess.check_output(["deno", "--version"], stderr=subprocess.STDOUT).decode()
        logger.info(f"✅ Deno detectado correctamente:\n{deno_version}")
    except Exception as e:
        logger.error(f"❌ ERROR: Deno no está instalado o no es accesible. YouTube HD podría fallar. Error: {e}")

    # Tarea en segundo plano para limpieza
    cleanup_task = asyncio.create_task(periodic_cleanup())

    logger.info("✅ FreeDownloaderPro API ready!")
    yield

    logger.info("🛑 FreeDownloaderPro API shutting down...")
    cleanup_task.cancel()
    await cleanup_temp_files()
    
    # Limpiar archivos temporales del combiner
    await cleanup_combiner_temp_files()
    
    logger.info("👋 Shutdown complete")

# ==========================================================
# FASTAPI APP
# ==========================================================
app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.API_VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan
)

# Rate Limiter Middleware
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================================
# ROUTERS CONFIGURATION - ESTRUCTURA COMPATIBLE CON FRONTEND
# ==========================================================
app.include_router(download_router, prefix="/api/v1", tags=["download"])
app.include_router(audio_router, prefix="/api/v1", tags=["audio"])
app.include_router(cookies_router, prefix="/api/v1", tags=["cookies"])
app.include_router(combiner_router, prefix="/api/v1", tags=["combiner"])
app.include_router(youtube_router, prefix="/api/v1/youtube", tags=["youtube"])  # ✅ YouTube routes específicas
app.include_router(facebook_router, prefix="/api/v1/facebook", tags=["facebook"])  # ✅ NUEVO: Facebook routes

# ==========================================================
# ROOT ENDPOINT
# ==========================================================
@app.get("/", response_class=JSONResponse)
async def root():
    """API Status - Compatible con frontend"""
    return {
        "name": settings.API_TITLE,
        "version": settings.API_VERSION,
        "status": "operational",
        "description": "API para descarga de videos de redes sociales",
        "endpoints": {
            "youtube": {
                "info": "POST /api/v1/youtube/download",
                "combined": "POST /api/v1/combiner/youtube/combine",
                "formats": "GET /api/v1/combiner/youtube/formats"
            },
            "tiktok": {
                "info": "POST /api/v1/tiktok/download",
                "audio": "POST /api/v1/tiktok/audio"
            },
            "facebook": {
                "info": "POST /api/v1/facebook/info",
                "video": "POST /api/v1/facebook/video", 
                "audio": "POST /api/v1/facebook/audio"
            },
            "audio": "GET /api/v1/audio",
            "health": "GET /api/v1/health",
            "cookies": "GET /api/v1/cookies/check"
        }
    }

# ==========================================================
# HEALTH CHECK
# ==========================================================
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "FreeDownloaderPro API",
        "version": settings.API_VERSION,
        "timestamp": datetime.now().isoformat(),
        "features": {
            "youtube_download": True,
            "tiktok_download": True,
            "facebook_download": True,
            "audio_extraction": True,
            "video_audio_combiner": True,
            "cookies_management": True
        },
        "routes_available": {
            "youtube": [
                "POST /api/v1/youtube/download",
                "POST /api/v1/combiner/youtube/combine",
                "GET /api/v1/combiner/youtube/formats"
            ],
            "tiktok": [
                "POST /api/v1/tiktok/download",
                "POST /api/v1/tiktok/audio"
            ],
            "facebook": [
                "POST /api/v1/facebook/info",
                "POST /api/v1/facebook/video",
                "POST /api/v1/facebook/audio"
            ],
            "general": [
                "GET /api/v1/audio",
                "GET /api/v1/health",
                "GET /api/v1/cookies/check"
            ]
        }
    }

# ==========================================================
# COOKIES CHECK ENDPOINTS
# ==========================================================
@app.get("/api/v1/cookies/check")
async def check_cookies():
    """Verificar estado de cookies"""
    path = Path(settings.YOUTUBE_COOKIES_PATH)
    return {
        "exists": path.exists(), 
        "path": str(path.resolve()),
        "valid": cookies_are_valid() if path.exists() else False,
        "last_updated": _last_cookie_update_attempt.isoformat() if _last_cookie_update_attempt else None
    }

# ==========================================================
# EXCEPTION HANDLERS
# ==========================================================
@app.exception_handler(SnapTubeError)
async def snaptube_exception_handler(request: Request, exc: SnapTubeError):
    """Handle SnapTube errors"""
    error_text = str(exc).lower()
    if any(keyword in error_text for keyword in ["cookies", "signin", "login", "auth"]):
        logger.warning("🔄 Error de cookies detectado. Intentando actualización automática...")
        if ensure_valid_cookies(force=True):
            return JSONResponse(
                status_code=503,
                content={
                    "status": "error", 
                    "message": "Cookies actualizadas, intente nuevamente.",
                    "type": "CookiesRefreshed"
                }
            )
        else:
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error", 
                    "message": "No se pudo actualizar cookies automáticamente.",
                    "type": "CookiesError"
                }
            )
    return JSONResponse(
        status_code=400,
        content={
            "status": "error", 
            "message": str(exc), 
            "type": "SnapTubeError"
        }
    )

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Rate limit exceeded"""
    return JSONResponse(
        status_code=429,
        content={
            "status": "error",
            "message": f"Rate limit exceeded: {exc.detail}",
            "type": "RateLimitError",
            "retry_after": "60 seconds"
        }
    )

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Not found"""
    return JSONResponse(
        status_code=404,
        content={
            "status": "error",
            "message": "Endpoint not found",
            "available_endpoints": {
                "youtube": [
                    "POST /api/v1/youtube/download",
                    "POST /api/v1/combiner/youtube/combine",
                    "GET /api/v1/combiner/youtube/formats"
                ],
                "tiktok": [
                    "POST /api/v1/tiktok/download",
                    "POST /api/v1/tiktok/audio"
                ],
                "facebook": [
                    "POST /api/v1/facebook/info",
                    "POST /api/v1/facebook/video",
                    "POST /api/v1/facebook/audio"
                ],
                "general": [
                    "GET /api/v1/audio",
                    "GET /api/v1/health",
                    "GET /api/v1/cookies/check",
                    "GET /"
                ]
            }
        }
    )

@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    """Internal server error"""
    logger.error(f"Internal server error: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": "error", 
            "message": "Internal server error", 
            "type": "InternalError",
            "support": "Contact support if this persists"
        }
    )

# ==========================================================
# BACKGROUND TASKS
# ==========================================================
async def periodic_cleanup():
    """Clean temporary files periodically"""
    while True:
        try:
            await cleanup_temp_files()
            await cleanup_combiner_temp_files()
            await asyncio.sleep(1800)  # 30 min
        except Exception as e:
            logger.error(f"💥 Periodic cleanup error: {str(e)}")
            await asyncio.sleep(3600)  # Esperar 1 hora si hay error

async def cleanup_temp_files():
    """Remove old temporary files"""
    try:
        import time
        current_time = time.time()
        cleaned = 0
        for filepath in settings.TEMP_DIR.glob("*"):
            if filepath.is_file():
                file_age = current_time - filepath.stat().st_mtime
                if file_age > settings.CLEANUP_INTERVAL:
                    try:
                        filepath.unlink()
                        cleaned += 1
                    except Exception as e:
                        logger.warning(f"⚠️ Could not delete {filepath}: {e}")
        if cleaned > 0:
            logger.info(f"🗑️ Cleaned {cleaned} temporary files")
    except Exception as e:
        logger.error(f"⚠️ Cleanup error: {str(e)}")

async def cleanup_combiner_temp_files():
    """Remove old combiner temporary files"""
    try:
        import shutil
        import tempfile
        import os
        import time
        
        current_time = time.time()
        temp_dir = tempfile.gettempdir()
        cleaned_dirs = 0
        cleaned_files = 0
        
        # Limpiar directorios temporales que empiecen con "yt_combiner_"
        for item in os.listdir(temp_dir):
            item_path = os.path.join(temp_dir, item)
            try:
                if item.startswith("yt_combiner_") and os.path.isdir(item_path):
                    # Verificar antigüedad del directorio
                    dir_age = current_time - os.path.getmtime(item_path)
                    if dir_age > settings.CLEANUP_INTERVAL:  # 1 hora
                        shutil.rmtree(item_path, ignore_errors=True)
                        cleaned_dirs += 1
                        logger.debug(f"🧹 Cleaned combiner temp directory: {item}")
                
                # También limpiar archivos temporales de combiner
                elif item.startswith("combined_") and (item.endswith(".mp4") or item.endswith(".webm")):
                    file_age = current_time - os.path.getmtime(item_path)
                    if file_age > settings.CLEANUP_INTERVAL:
                        os.unlink(item_path)
                        cleaned_files += 1
                        logger.debug(f"🧹 Cleaned combiner temp file: {item}")
                        
            except Exception as e:
                logger.warning(f"⚠️ Could not clean temp item {item}: {e}")
        
        if cleaned_dirs > 0 or cleaned_files > 0:
            logger.info(f"🧹 Cleaned {cleaned_dirs} combiner directories and {cleaned_files} files")
            
    except Exception as e:
        logger.error(f"⚠️ Combiner cleanup error: {str(e)}")

# ==========================================================
# API STATUS ENDPOINT
# ==========================================================
@app.get("/api/v1/status")
async def api_status():
    """Detailed API status information"""
    from app.services.facebook_service import FacebookExtractor
    from app.services.tiktok_service import TikTokService
    
    services_status = {
        "youtube": {
            "status": "operational",
            "cookies_valid": cookies_are_valid(),
            "extractor": "yt-dlp"
        },
        "facebook": {
            "status": "operational", 
            "extractor": "FacebookExtractor",
            "methods": ["yt-dlp", "manual_scraping", "mobile_fallback"]
        },
        "tiktok": {
            "status": "operational",
            "extractor": "TikTokService", 
            "methods": ["oembed", "embed_scraping"]
        },
        "combiner": {
            "status": "operational",
            "service": "YouTubeCombinerService"
        }
    }
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": settings.API_VERSION,
        "services": services_status,
        "environment": "production" if not settings.DEBUG else "development",
        "rate_limiting": {
            "enabled": True,
            "strategy": "fixed_window"
        }
    }

# ==========================================================
# MAIN ENTRY
# ==========================================================
if __name__ == "__main__":
    logger.info("🚀 Iniciando FreeDownloaderPro API...")
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        access_log=True,
        log_level=settings.LOG_LEVEL.lower(),
        workers=1
    )