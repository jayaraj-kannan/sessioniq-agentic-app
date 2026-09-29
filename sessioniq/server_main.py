import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.fast_api_app import app

# Check for frontend_dist
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend_dist"))
if not os.path.exists(frontend_dir):
    frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))

if os.path.exists(frontend_dir):
    assets_dir = os.path.join(frontend_dir, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        target = os.path.join(frontend_dir, full_path)
        if os.path.isfile(target):
            return FileResponse(target)
        index_file = os.path.join(frontend_dir, "index.html")
        if os.path.isfile(index_file):
            return FileResponse(index_file)
        return {"message": "Frontend build not found"}
