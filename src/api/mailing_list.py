from fastapi import APIRouter, HTTPException, Request
from resend.exceptions import ResendError

from src.core.limiter import limiter
from src.models.mailing_list_models.mailing_list import MailingListSubscribe, MailingListSubscribeResponse
from src.services.email import subscribe_to_mailing_list

router = APIRouter()


@router.post("/subscribe", response_model=MailingListSubscribeResponse)
@limiter.limit("5/minute")
async def subscribe(request: Request, body: MailingListSubscribe):
    try:
        subscribe_to_mailing_list(body.email)
    except ResendError:
        raise HTTPException(status_code=502, detail="Failed to subscribe to mailing list")
    return MailingListSubscribeResponse(status="subscribed")
