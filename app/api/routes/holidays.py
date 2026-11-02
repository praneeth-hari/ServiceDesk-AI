from typing import Optional, Sequence
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.holiday import HolidayCreate, HolidayRead
from app.services.holidays import create_holiday, delete_holiday, list_holidays

router = APIRouter(prefix="/holidays", tags=["holidays"])


@router.post(
    "",
    response_model=HolidayRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new holiday (Admin only)",
)
def create_new_holiday(
    holiday_in: HolidayCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
) -> HolidayRead:
    """
    Register a new official public holiday. Requires Admin role.
    Returns 409 Conflict if date is already registered.
    """
    return create_holiday(db, holiday_in=holiday_in, current_user=current_user)


@router.get(
    "",
    response_model=list[HolidayRead],
    status_code=status.HTTP_200_OK,
    summary="List holidays (Agent and Admin only)",
)
def get_all_holidays(
    year: Optional[int] = Query(default=None, description="Filter holidays by calendar year"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN, UserRole.AGENT])),
) -> Sequence[HolidayRead]:
    """
    List holidays ordered chronologically. Requires Agent or Admin role.
    """
    return list_holidays(db, current_user=current_user, year=year)


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a holiday (Admin only)",
)
def remove_holiday(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.ADMIN])),
) -> None:
    """
    Delete a holiday by ID. Requires Admin role.
    """
    delete_holiday(db, holiday_id=id, current_user=current_user)
