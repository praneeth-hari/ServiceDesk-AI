from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.triage import TriageSuggestRequest, TriageSuggestResponse
from app.services.triage import suggest

router = APIRouter(prefix="/triage", tags=["triage"])


@router.post(
    "/suggest",
    response_model=TriageSuggestResponse,
    status_code=status.HTTP_200_OK,
    summary="Get category/priority suggestions and duplicate detection",
)
def get_triage_suggestions(
    payload: TriageSuggestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TriageSuggestResponse:
    """
    Provide advisory category/priority suggestions and duplicate ticket detection.
    Accessible to all authenticated users. Respects privacy filters for requesters.
    """
    result = suggest(
        db=db,
        title=payload.title,
        description=payload.description,
        current_user=current_user,
    )
    return TriageSuggestResponse(**result)
