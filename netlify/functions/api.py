"""Netlify Functions entrypoint for the FastAPI app."""

from mangum import Mangum

from app.api.main import app

# Lambda-compatible handler Netlify invokes for Python functions.
handler = Mangum(app)

