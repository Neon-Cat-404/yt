import os
import uuid
import subprocess
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="YouTube Downloader")

DOWNLOAD_DIR = Path("/tmp/downloads")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

jobs = {}


class JobRequest(BaseModel):
    url: str


@app.get("/")
def home():
    return {
        "status": "online",
        "service": "YouTube Downloader",
        "max_resolution": "720p"
    }


@app.post("/jobs")
def create_job(request: JobRequest):
    job_id = str(uuid.uuid4())

    output_template = str(DOWNLOAD_DIR / f"{job_id}.%(ext)s")

    jobs[job_id] = {
        "status": "processing",
        "url": request.url
    }

    try:
        command = [
            "yt-dlp",
            "--no-playlist",
            "-f",
            "bv*[height<=720]+ba/b[height<=720]",
            "--merge-output-format",
            "mp4",
            "-o",
            output_template,
            request.url
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=600
        )

        if result.returncode != 0:
            jobs[job_id] = {
                "status": "failed",
                "error": result.stderr[-2000:]
            }

            raise HTTPException(
                status_code=500,
                detail=result.stderr[-4000:]
            )

        output_file = DOWNLOAD_DIR / f"{job_id}.mp4"

        if not output_file.exists():
            # Find whatever yt-dlp produced
            possible_files = list(
                DOWNLOAD_DIR.glob(f"{job_id}.*")
            )

            if not possible_files:
                jobs[job_id] = {
                    "status": "failed",
                    "error": "Output file was not created"
                }

                raise HTTPException(
                    status_code=500,
                    detail="Output file was not created"
                )

            output_file = possible_files[0]

        jobs[job_id] = {
            "status": "completed",
            "filename": output_file.name
        }

        return {
            "job_id": job_id,
            "status": "completed",
            "download_url": f"/download/{job_id}"
        }

    except subprocess.TimeoutExpired:
        jobs[job_id] = {
            "status": "failed",
            "error": "Download timed out"
        }

        raise HTTPException(
            status_code=504,
            detail="Download timed out"
        )


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job not found"
        )

    response = {
        "job_id": job_id,
        **job
    }

    if job.get("status") == "completed":
        response["download_url"] = f"/download/{job_id}"

    return response


@app.get("/download/{job_id}")
def download(job_id: str):
    job = jobs.get(job_id)

    if not job or job.get("status") != "completed":
        raise HTTPException(
            status_code=404,
            detail="File not found"
        )

    file_path = DOWNLOAD_DIR / job["filename"]

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="File no longer exists"
        )

    return FileResponse(
        file_path,
        media_type="video/mp4",
        filename=f"{job_id}.mp4"
    )
