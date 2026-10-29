"""
FastAPI Web Application for Keyword Analysis Engine.

Provides an interactive web interface with:
- Seed keyword discovery form
- Live progress and real-time execution
- Clustered view (One page per cluster)
- Detailed metrics breakdown (demand proxy, competition estimate, specificity, intent)
- CSV direct download
- Discarded keywords inspection log
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from keyword_analysis.config import load_config
from keyword_analysis.pipeline import KeywordPipeline
from keyword_analysis.utils.logger import get_logger

log = get_logger(__name__)

app = FastAPI(title="Free SEO Keyword Analysis Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Cached pipeline instance
_pipeline: Optional[KeywordPipeline] = None
_last_result = None


def get_pipeline() -> KeywordPipeline:
    global _pipeline
    if _pipeline is None:
        cfg = load_config()
        _pipeline = KeywordPipeline(cfg)
    return _pipeline


from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response

INDEX_HTML_PATH = TEMPLATES_DIR / "index.html"


@app.get("/", response_class=HTMLResponse)
async def index():
    if INDEX_HTML_PATH.exists():
        with open(INDEX_HTML_PATH, "r", encoding="utf-8") as f:
            return HTMLResponse(
                content=f.read(),
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )
    return HTMLResponse("<h1>KeyProspector</h1>")


@app.post("/api/analyze")
async def analyze_keyword(
    seed: str = Form(...),
    keep_thresh: Optional[float] = Form(None),
    seed_thresh: Optional[float] = Form(None),
):
    global _last_result
    seed = seed.strip()
    if not seed:
        raise HTTPException(status_code=400, detail="Seed topic cannot be empty.")

    pipeline = get_pipeline()
    
    # Check for Gemini API key if enabled
    if pipeline.cfg.providers.gemini and not pipeline.cfg.gemini.api_key:
        log.warning("Gemini is enabled but API key is missing. Results will use algorithmic fallback.")
    
    if keep_thresh is not None:
        pipeline.cfg.thresholds.keep_threshold = keep_thresh
    if seed_thresh is not None:
        pipeline.cfg.thresholds.seed_threshold = seed_thresh

    result = pipeline.run(seed)
    _last_result = result

    return {
        "status": "success",
        "seed": result.seed,
        "elapsed_seconds": result.execution_time_seconds,
        "total_raw": result.total_raw_candidates,
        "enriched": result.enriched_count,
        "kept": result.kept_count,
        "discarded": result.discarded_count,
        "clusters_count": result.clusters_count,
        "data": result.output_dict,
        "discarded_sample": [
            {"text": d.text, "reason": d.reason} for d in result.discarded[:20]
        ],
    }


@app.get("/api/download/csv")
async def download_csv():
    global _last_result
    if _last_result is None or not _last_result.csv_data:
        raise HTTPException(status_code=404, detail="No keyword analysis result available to export.")

    filename = f"keywords_{_last_result.seed.replace(' ', '_')}.csv"
    return Response(
        content=_last_result.csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("keyword_analysis.web.app:app", host="127.0.0.1", port=8000, reload=True)
