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
