import hashlib
import re
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from ..db import get_db
from ..ingest.extract import SUPPORTED_SUFFIXES
from ..ingest.service import process_documents

router = APIRouter()

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _doc_out(doc: models.Document) -> schemas.DocumentOut:
    doc_type = (doc.extracted_json or {}).get("doc_type") if doc.extracted_json else None
    return schemas.DocumentOut(
        id=doc.id,
        filename=doc.filename,
        mime=doc.mime,
        size_bytes=doc.size_bytes,
        status=doc.status,
        error=doc.error,
        doc_type=doc_type,
        uploaded_at=doc.uploaded_at,
        processed_at=doc.processed_at,
    )


def _profile_or_404(db: Session, profile_id: str) -> models.Profile:
    profile = db.get(models.Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


def _safe_name(filename: str) -> str:
    name = Path(filename).name
    return re.sub(r"[^A-Za-z0-9._\- \[\]()]+", "_", name)[:140] or "document"


@router.get("", response_model=list[schemas.DocumentOut])
def list_documents(profile_id: str, db: Session = Depends(get_db)):
    _profile_or_404(db, profile_id)
    docs = (
        db.query(models.Document)
        .filter(models.Document.profile_id == profile_id)
        .order_by(models.Document.uploaded_at)
        .all()
    )
    return [_doc_out(d) for d in docs]


@router.post("", response_model=list[schemas.DocumentOut], status_code=201)
async def upload_documents(
    profile_id: str,
    background: BackgroundTasks,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    _profile_or_404(db, profile_id)
    upload_dir = settings.files_dir / profile_id / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    results: list[models.Document] = []
    to_process: list[str] = []

    for file in files:
        raw = await file.read()
        filename = _safe_name(file.filename or "document")
        suffix = Path(filename).suffix.lower()

        if len(raw) > MAX_UPLOAD_BYTES:
            doc = models.Document(
                profile_id=profile_id,
                filename=filename,
                mime=file.content_type or "application/octet-stream",
                sha256=hashlib.sha256(raw).hexdigest(),
                size_bytes=len(raw),
                path="",
                status="failed",
                error="File is larger than 25 MB.",
            )
            db.add(doc)
            results.append(doc)
            continue

        if suffix not in SUPPORTED_SUFFIXES:
            doc = models.Document(
                profile_id=profile_id,
                filename=filename,
                mime=file.content_type or "application/octet-stream",
                sha256=hashlib.sha256(raw).hexdigest(),
                size_bytes=len(raw),
                path="",
                status="failed",
                error=f"Unsupported file type '{suffix}'. Supported: PDF, DOCX, TXT, MD, PNG, JPG, WEBP, GIF.",
            )
            db.add(doc)
            results.append(doc)
            continue

        sha = hashlib.sha256(raw).hexdigest()
        existing = (
            db.query(models.Document)
            .filter(
                models.Document.profile_id == profile_id,
                models.Document.sha256 == sha,
                models.Document.status != "failed",
            )
            .first()
        )
        if existing is not None:
            results.append(existing)  # idempotent: same bytes already uploaded
            continue

        doc = models.Document(
            profile_id=profile_id,
            filename=filename,
            mime=file.content_type or "application/octet-stream",
            sha256=sha,
            size_bytes=len(raw),
            path="",
        )
        db.add(doc)
        db.flush()  # assign id for the on-disk name
        dest = upload_dir / f"{doc.id}_{filename}"
        dest.write_bytes(raw)
        doc.path = str(dest)
        results.append(doc)
        to_process.append(doc.id)

    db.commit()
    if to_process:
        background.add_task(process_documents, to_process)
    return [_doc_out(d) for d in results]


@router.post("/{doc_id}/retry", response_model=schemas.DocumentOut)
def retry_document(
    profile_id: str, doc_id: str, background: BackgroundTasks, db: Session = Depends(get_db)
):
    doc = db.get(models.Document, doc_id)
    if doc is None or doc.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.status != "failed":
        raise HTTPException(status_code=409, detail="Only failed documents can be retried.")
    if not doc.path or not Path(doc.path).exists():
        raise HTTPException(
            status_code=409, detail="Original file is gone — delete this entry and re-upload."
        )
    doc.status = "uploaded"
    doc.error = None
    db.commit()
    background.add_task(process_documents, [doc.id])
    return _doc_out(doc)


@router.delete("/{doc_id}", status_code=204)
def delete_document(profile_id: str, doc_id: str, db: Session = Depends(get_db)):
    doc = db.get(models.Document, doc_id)
    if doc is None or doc.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.path:
        Path(doc.path).unlink(missing_ok=True)
    db.delete(doc)
    db.commit()
