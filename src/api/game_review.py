from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from src.api.games import map_game_to_read
from src.api.users import require_admin
from src.core.exceptions import GAME_NOT_FOUND_EXCEPTION
from src.db.database import get_db
from src.db.tables import Game, GameReport
from src.models.game_models.game import GameRead
from src.models.game_models.game_review import GameReportAdminRead, GameReportResolvePatch, GameReviewPatch
from src.services import notifications

admin_router = APIRouter()

_GAME_JOINEDLOADS = (
    joinedload(Game.equipment_items),
    joinedload(Game.setting_items),
    joinedload(Game.contributor),
    joinedload(Game.alias_objects),
    joinedload(Game.photos),
)


def _set_game_review_status(
    db: Session,
    game: Game,
    status: str,
    reason_code: str | None,
    reason_detail: str | None,
    admin_id: str,
) -> None:
    game.status = status
    game.rejection_reason_code = reason_code if status == "rejected" else None
    game.rejection_reason = reason_detail if status == "rejected" else None
    game.reviewed_by = admin_id
    game.reviewed_at = datetime.now(timezone.utc)
    notifications.send_game_status_notification(
        db, game.contributor_id, game.id, game.name, status, reason_code, reason_detail
    )


@admin_router.get("/games/pending", response_model=List[GameRead])
def list_pending_games(
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    games = (
        db.query(Game)
        .options(*_GAME_JOINEDLOADS)
        .filter(Game.status == "pending")
        .order_by(Game.created_at.asc())
        .all()
    )
    return [map_game_to_read(g) for g in games]


@admin_router.patch("/games/{game_id}/review", response_model=GameRead)
def review_game(
    game_id: str,
    body: GameReviewPatch,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    if body.status not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="status must be 'approved' or 'rejected'")
    if body.status == "rejected" and not body.rejection_reason_code:
        raise HTTPException(status_code=422, detail="rejection_reason_code is required when rejecting a game")

    game = (
        db.query(Game)
        .options(*_GAME_JOINEDLOADS)
        .filter(Game.id == game_id)
        .first()
    )
    if not game:
        raise GAME_NOT_FOUND_EXCEPTION

    reason_code = body.rejection_reason_code.value if body.rejection_reason_code else None
    _set_game_review_status(db, game, body.status, reason_code, body.rejection_reason, current_user.id)
    db.commit()
    db.refresh(game)
    return map_game_to_read(game)


@admin_router.get("/games/reports", response_model=List[GameReportAdminRead])
def list_pending_reports(
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    reports = (
        db.query(GameReport)
        .options(joinedload(GameReport.game), joinedload(GameReport.reporter))
        .filter(GameReport.status == "pending")
        .order_by(GameReport.created_at.asc())
        .all()
    )
    return [
        GameReportAdminRead(
            id=r.id,
            game_id=r.game_id,
            game_name=r.game.name if r.game else "",
            reporter_id=r.reporter_id,
            reporter_username=r.reporter.username if r.reporter else "",
            reason=r.reason,
            status=r.status,
            created_at=r.created_at,
        )
        for r in reports
    ]


@admin_router.patch("/games/reports/{report_id}", response_model=GameReportAdminRead)
def resolve_report(
    report_id: str,
    body: GameReportResolvePatch,
    db: Session = Depends(get_db),
    current_user=Depends(require_admin),
):
    if body.action not in ("dismiss", "reject"):
        raise HTTPException(status_code=422, detail="action must be 'dismiss' or 'reject'")
    if body.action == "reject" and not body.rejection_reason_code:
        raise HTTPException(status_code=422, detail="rejection_reason_code is required when rejecting a game")

    report = (
        db.query(GameReport)
        .options(joinedload(GameReport.game), joinedload(GameReport.reporter))
        .filter(GameReport.id == report_id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if body.action == "dismiss":
        report.status = "dismissed"
    else:
        report.status = "actioned"
        if not report.game:
            raise GAME_NOT_FOUND_EXCEPTION
        reason_detail = body.reason or f"Reported: {report.reason}"
        _set_game_review_status(
            db, report.game, "rejected", body.rejection_reason_code.value, reason_detail, current_user.id
        )

    db.commit()
    db.refresh(report)

    return GameReportAdminRead(
        id=report.id,
        game_id=report.game_id,
        game_name=report.game.name if report.game else "",
        reporter_id=report.reporter_id,
        reporter_username=report.reporter.username if report.reporter else "",
        reason=report.reason,
        status=report.status,
        created_at=report.created_at,
    )
