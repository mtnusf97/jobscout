from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import credentials, schemas
from ..db import get_db

router = APIRouter()


@router.get("", response_model=list[schemas.CredentialStateOut])
def list_credentials(db: Session = Depends(get_db)):
    return credentials.list_states(db)


@router.put("/{name}", response_model=schemas.CredentialResultOut)
def set_credential(name: str, body: schemas.CredentialSetIn, db: Session = Depends(get_db)):
    try:
        return credentials.set_credential(db, name, body.value)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown credential '{name}'")


@router.post("/{name}/validate", response_model=schemas.CredentialResultOut)
def revalidate_credential(name: str, db: Session = Depends(get_db)):
    try:
        return credentials.revalidate(db, name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown credential '{name}'")
    except LookupError:
        raise HTTPException(status_code=409, detail=f"Credential '{name}' is not set yet")


@router.delete("/{name}", status_code=204)
def delete_credential(name: str, db: Session = Depends(get_db)):
    try:
        credentials.delete_credential(db, name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown credential '{name}'")
