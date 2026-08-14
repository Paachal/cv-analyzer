"""
Convenience runner: `python run.py` starts the API on http://localhost:8000
with auto-reload for local development.
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
