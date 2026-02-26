from fastapi import (
    APIRouter,
    Depends,
    Request,
    Query,
    UploadFile,
    File,
    HTTPException,
    BackgroundTasks,
)
from starlette.background import BackgroundTask
import os
from fastapi.responses import FileResponse
from pathlib import Path
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from src.auth.model import Guest, Job
from fastapi.concurrency import run_in_threadpool
from src.core.session import SessionLocal

from src.core.session import get_db

from src.auth.service import AuthService
from src.auth.schema import (
    Token,
    HostCreate,
    HostResponse,
)
import tempfile
import boto3
from src.auth.repository import get_current_host
from src.auth.model import Host


BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
    region_name="eu-central-1",
)

router = APIRouter()
auth_service = AuthService()


@router.post("/login", response_model=Token)
async def login(
    db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()
):
    """Login endpoint"""
    return auth_service.login(db, form_data.username, form_data.password)


@router.post("/register", response_model=HostResponse)
async def register(
    request: Request,
    host_data: HostCreate,
    db: Session = Depends(get_db),
):
    """Host registration endpoint - requires API key"""
    full_url = str(request.url).rstrip("/").replace("/register", "")
    return auth_service.register(db, host_data, full_url)


@router.get(
    "/validate-token",
    responses={
        400: {"description": "Host inactive"},
        401: {"description": "Invalid, expired, or missing token"},
    },
)
async def validate_api_token(current_host: Host = Depends(get_current_host)):
    """
    Validates the host's access token.

    It checks:
    1.  The token's signature and expiration using `decode_access_token`.
    2.  If the host associated with the token's 'sub' claim (host ID)
        still exists in the database and is active.

    Returns 200 OK if the token is valid and the host is active.
    Raises 401 Unauthorized if the token is invalid/expired/missing, or host not found.
    Raises 400 Bad Request if the host is found but inactive.
    """
    return {"message": "Token is valid"}


@router.get(
    "/get_host",
    responses={
        401: {"description": "Unauthorized - Invalid, expired, or missing token"},
        404: {"description": "Host not found"},
    },
)
async def get_hosts(
    db: Session = Depends(get_db),
    current_host: Host = Depends(get_current_host),
):
    """Login endpoint"""
    return auth_service.get_all_hosts(db, current_host.email)


@router.get(
    "/activate_host",
    responses={
        401: {"description": "Unauthorized - Invalid, expired, or missing token"},
        404: {"description": "Host not found"},
    },
)
async def activate_host(
    db: Session = Depends(get_db),
    current_host: Host = Depends(get_current_host),
    host_email=Query(str, description="The host email that needs activation."),
):
    """Login endpoint"""
    return auth_service.activate_host(db, host_email)


@router.post("/process-invitation-file")
async def process_invitation_file(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_host: Host = Depends(get_current_host),
    invitation_name: str = Query(..., description="Invitation name"),
    file: UploadFile = File(...),
):
    """
    Upload an Excel file, add column 'x',
    save it inside src/excel, and return it.
    """

    # Read file contents NOW (before the request closes)
    contents = await file.read()
    job = Job(status="pending")
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(
        run_in_threadpool, run_generate_images, job.id, contents, invitation_name
    )
    # Ensure parent directory exists
    return {"job_id": job.id}


def run_generate_images(job_id: str, contents: bytes, invitation_name: str):
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        job.status = "running"
        db.commit()
        zip_path = auth_service.generate_images(db, contents, invitation_name)
        job.status = "done"
        job.result = str(zip_path)
        db.commit()
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        job.status = "error"
        job.error = str(e)
        db.commit()
    finally:
        db.close()


@router.get("/invitation-job/{job_id}")
def get_job_status(
    job_id: str,
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": job.status, "error": job.error}


@router.get("/invitation-job/{job_id}/download")
def download_job_result(
    job_id: str,
    db: Session = Depends(get_db),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job or job.status != "done":
        raise HTTPException(status_code=400, detail="Not ready")

    temp_file = tempfile.NamedTemporaryFile(delete=False)
    temp_file.close()
    # delete the zip file
    base_path = Path("src") / f"excel/{(job.result).split('/')[-1]}"
    if base_path.exists():
        base_path.unlink()

    try:
        s3.download_file(BUCKET_NAME, job.result, temp_file.name)
    except Exception:
        os.remove(temp_file.name)
        raise

    return FileResponse(
        temp_file.name,
        filename=(job.result).split("/")[-1],
        background=BackgroundTask(os.remove, temp_file.name),
    )


@router.get("/excel_files")
async def list_files(
    db: Session = Depends(get_db),
    current_host: Host = Depends(get_current_host),
):

    files = db.query(Guest.event_name, Guest.event_id).distinct().all()
    if not files:
        return
    files = [f"{i.event_name}_{i.event_id}.zip" for i in files]
    return {"files": files}


@router.get("/images_folders")
async def list_folders(
    db: Session = Depends(get_db),
    current_host: Host = Depends(get_current_host),
):
    folders = db.query(Guest.event_name, Guest.event_id).distinct().all()
    if not folders:
        return
    folders = [i.event_id for i in folders]
    return {"folders": folders}


@router.get("/images_files/{id}")
async def list_images(
    id: str | int,
    db: Session = Depends(get_db),
    current_host: Host = Depends(get_current_host),
):
    images = db.query(Guest).filter(Guest.event_id == id).all()
    images = [f"{i.code}-{i.name}_{i.id}" for i in images]

    return {"images": images}


@router.get("/image_file/{id}")
async def get_image(
    id: str | int,
    img_name: str | int,
    current_host: Host = Depends(get_current_host),
):
    image_path = f"images/{id}/{img_name}.png"
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    temp_file.close()

    try:
        s3.download_file(BUCKET_NAME, image_path, temp_file.name)
    except Exception:
        os.remove(temp_file.name)
        raise

    return FileResponse(
        temp_file.name,
        filename=image_path.split("/")[-1],
        background=BackgroundTask(os.remove, temp_file.name),
    )


@router.get("/excel_file/{excel_name}")
async def get_excel(
    excel_name: str | int,
    current_host: Host = Depends(get_current_host),
):
    zipfile_name = f"zip_files/{excel_name}"
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    temp_file.close()

    try:
        s3.download_file(BUCKET_NAME, zipfile_name, temp_file.name)
    except Exception:
        os.remove(temp_file.name)
        raise

    return FileResponse(
        temp_file.name,
        filename=zipfile_name.split("/")[-1],
        background=BackgroundTask(os.remove, temp_file.name),
    )


@router.get("/invitation_data/{id}")
async def get_invitation_data(
    id: str | int,
    db: Session = Depends(get_db),
    current_host: Host = Depends(get_current_host),
):
    guests = db.query(Guest).filter(Guest.event_id == id).all()
    return guests
