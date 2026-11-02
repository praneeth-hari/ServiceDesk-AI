from datetime import date
from typing import Optional, Sequence
from fastapi import HTTPException, status
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.holiday import Holiday
from app.models.user import User
from app.schemas.holiday import HolidayCreate


def get_holiday_by_date(db: Session, holiday_date: date) -> Optional[Holiday]:
    """Retrieve a holiday record by exact date."""
    return db.scalars(sa.select(Holiday).where(Holiday.holiday_date == holiday_date)).first()


def get_holiday_by_id(db: Session, holiday_id: int) -> Optional[Holiday]:
    """Retrieve a holiday record by primary key."""
    return db.get(Holiday, holiday_id)


def get_holiday_dates(db: Session) -> set[date]:
    """Retrieve all holiday dates as a set for efficient business-time calculations."""
    stmt = sa.select(Holiday.holiday_date)
    return set(db.scalars(stmt).all())


def create_holiday(db: Session, holiday_in: HolidayCreate, current_user: User) -> Holiday:
    """
    Create a new public holiday (Admin only).
    Fails with 409 Conflict if a holiday already exists on the given date.
    """
    existing = get_holiday_by_date(db, holiday_in.holiday_date)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A holiday on {holiday_in.holiday_date} already exists",
        )

    holiday = Holiday(
        holiday_date=holiday_in.holiday_date,
        name=holiday_in.name,
    )
    db.add(holiday)
    db.commit()
    db.refresh(holiday)
    return holiday


def list_holidays(
    db: Session,
    current_user: User,
    year: Optional[int] = None,
) -> Sequence[Holiday]:
    """
    List public holidays ordered chronologically.
    Optionally filter by year.
    """
    stmt = sa.select(Holiday)
    if year is not None:
        stmt = stmt.where(sa.extract("year", Holiday.holiday_date) == year)

    stmt = stmt.order_by(Holiday.holiday_date.asc(), Holiday.id.asc())
    return db.scalars(stmt).all()


def delete_holiday(db: Session, holiday_id: int, current_user: User) -> None:
    """
    Delete a holiday by ID (Admin only).
    Fails with 404 Not Found if missing.
    """
    holiday = get_holiday_by_id(db, holiday_id)
    if not holiday:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Holiday not found",
        )

    db.delete(holiday)
    db.commit()
