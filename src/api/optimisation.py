# src/api/optimisation.py
from fastapi import APIRouter, HTTPException, Depends, status

from src.api.users import get_current_active_user
from src.db.tables import User
from src.models.enums.ai_agents_enum import AIAgentEnum
from src.models.optimisation_models.optimisation_models import OptimisationResponse
from src.services.optimiser import get_optimiser

router = APIRouter()


def auth_required():
    return Depends(get_current_active_user)


@router.post("/", response_model=OptimisationResponse)
async def optimise_text(field_name: str, original_text: str, _current_user: User = auth_required()):
    valid_types = [e.value for e in AIAgentEnum]

    # 1. Validate Input Type
    if field_name not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid field '{field_name}'. Valid options: {', '.join(valid_types)}"
        )

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
