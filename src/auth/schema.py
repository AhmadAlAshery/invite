from typing import Optional
from pydantic import (
    BaseModel,
    EmailStr,
    SecretStr,
    ConfigDict,
)


class HostBase(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class HostCreate(HostBase):
    password: SecretStr
    model_config = ConfigDict(from_attributes=True)


class HostResponse(HostBase):
    is_active: bool

    model_config = {"from_attributes": True, "extra": "allow"}


class Token(BaseModel):
    access_token: str
    token_type: str
