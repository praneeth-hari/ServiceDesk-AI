from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.db.session import get_db
from app.schemas.token import Token
from app.schemas.user import UserCreate, UserLogin, UserRead
from app.services.users import authenticate_user, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
def register(user_in: UserCreate, db: Session = Depends(get_db)) -> UserRead:
    """
    Register a new user account. Defaults to requester role.
    """
    user = register_user(db, user_in=user_in)
    return user


@router.post(
    "/login",
    response_model=Token,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and receive a JWT access token",
)
def login(credentials: UserLogin, db: Session = Depends(get_db)) -> Token:
    """
    Authenticate with email and password, returning a signed JWT access token.
    """
    user = authenticate_user(db, email=credentials.email, password=credentials.password)
    access_token = create_access_token(data={"sub": str(user.id)})
    return Token(access_token=access_token, token_type="bearer")
