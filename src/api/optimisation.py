# src/api/optimisation.py
from fastapi import APIRouter, HTTPException, Depends, status

from src.api.users import get_current_active_user
from src.db.tables import User
from src.models.enums.ai_agents_enum import AIAgentEnum
from src.models.optimisation_models.optimisation_models import OptimisationRequest, OptimisationResponse
from src.models.optimisation_models.brain_dump_models import BrainDumpRequest, BrainDumpResponse
from src.services.moderation import check_content
from src.services.optimiser import get_optimiser
from src.services.brain_dump import get_brain_dump_splitter, MIN_DUMP_LENGTH, FIELDS

router = APIRouter()

MAX_DUMP_LENGTH = 4000


def auth_required():
    return Depends(get_current_active_user)


@router.post("/", response_model=OptimisationResponse)
async def optimise_text(request: OptimisationRequest, _current_user: User = auth_required()):
    field_name = request.field_type
    original_text = request.original_text
    valid_types = [e.value for e in AIAgentEnum]

    # 1. Validate Input Type
    if field_name not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid field '{field_name}'. Valid options: {', '.join(valid_types)}"
        )

    if not check_content(original_text):
        raise HTTPException(status_code=422, detail="Content violates community guidelines.")

    # 2. Get Optimizer and Run Logic
    optimizer = get_optimiser(field_name)
    result_data = optimizer.optimise(original_text)  # This returns an OptimisationResult

    # 3. Transform into OptimisationResponse
    # Check if successful based on the status field in the result
    is_success = result_data.status == "success"

    # Construct the response model manually for clarity and flexibility
    response_model: OptimisationResponse = OptimisationResponse(
        success=is_success,
        data=result_data if is_success else None,  # Only include data if successful
        error_message=result_data.note if not is_success else None
    )

    return response_model


@router.post("/brain-dump", response_model=BrainDumpResponse)
async def brain_dump(request: BrainDumpRequest, _current_user: User = auth_required()):
    dump = request.dump_text.strip()

    if len(dump) < MIN_DUMP_LENGTH:
        return BrainDumpResponse(
            success=False,
            data=None,
            missing_fields=[],
            error_message="Text too short to split.",
        )

    if len(dump) > MAX_DUMP_LENGTH:
        raise HTTPException(status_code=422, detail="Brain dump text is too long (max 4000 characters).")

    if not check_content(dump):
        raise HTTPException(status_code=422, detail="Content violates community guidelines.")

    result, missing, error = get_brain_dump_splitter().split(dump)

    if result is None:
        return BrainDumpResponse(
            success=False, data=None, missing_fields=[], error_message=error
        )

    for field_name in FIELDS:
        raw_value = getattr(result, field_name)
        if not raw_value:
            continue
        optimised = get_optimiser(field_name).optimise(raw_value)
        if optimised.status == "success":
            setattr(result, field_name, optimised.optimized)

    return BrainDumpResponse(
        success=True, data=result, missing_fields=missing, error_message=None
    )
