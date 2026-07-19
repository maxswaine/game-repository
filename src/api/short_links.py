from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from src.api.users import require_admin
from src.db.database import get_db
from src.db.tables import ShortLink
from src.models.short_link_models.short_link import (
    ShortLinkCreate,
    ShortLinkPatch,
    ShortLinkRead,
)

public_router = APIRouter()
admin_router = APIRouter()


@public_router.get("/qr/{code}")
def redirect_short_link(code: str, db: Session = Depends(get_db)):
    link = db.query(ShortLink).filter(ShortLink.code == code).first()
    if not link or not link.is_active:
        raise HTTPException(status_code=404, detail="Link not found")
    link.scan_count += 1
    db.commit()
    return RedirectResponse(link.target_url, status_code=302)


@admin_router.post("/links", response_model=ShortLinkRead, status_code=201)
def create_short_link(
    body: ShortLinkCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    if db.query(ShortLink).filter(ShortLink.code == body.code).first():
        raise HTTPException(status_code=409, detail="Code already exists")
    link = ShortLink(code=body.code, target_url=body.target_url, label=body.label)
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


@admin_router.get("/links", response_model=list[ShortLinkRead])
def list_short_links(
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    return db.query(ShortLink).all()


@admin_router.patch("/links/{code}", response_model=ShortLinkRead)
def update_short_link(
    code: str,
    body: ShortLinkPatch,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    link = db.query(ShortLink).filter(ShortLink.code == code).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    if body.target_url is not None:
        link.target_url = body.target_url
    if body.label is not None:
        link.label = body.label
    if body.is_active is not None:
        link.is_active = body.is_active
    link.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(link)
    return link


@admin_router.delete("/links/{code}", status_code=204)
def delete_short_link(
    code: str,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    link = db.query(ShortLink).filter(ShortLink.code == code).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    db.delete(link)
    db.commit()
