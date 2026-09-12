# schemas/__init__.py - Validated external request contracts.
from typing import Literal
from pydantic import BaseModel, EmailStr, Field


class Credentials(BaseModel):
    """Bound password sizes to protect the password hashing service."""
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class Register(Credentials):
    """Require a display name for human-readable contact views."""
    display_name: str = Field(min_length=1, max_length=80)


class ProfileUpdate(BaseModel):
    """Verification cannot be self-assigned through ordinary profile updates."""
    display_name: str = Field(min_length=1, max_length=80)
    emergency_contact: str = Field(default="", max_length=200)
    community_opt_in: bool = False


class ContactInput(BaseModel):
    """Contacts must correspond to an existing Trail account."""
    email: EmailStr


class SessionInput(BaseModel):
    """Consent is a per-session selection of already approved contacts."""
    share_with: list[str] = Field(default_factory=list, max_length=20)
    community_enabled: bool = False


class LocationInput(BaseModel):
    """Speed is calculated server-side from coordinates and timestamps."""
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    timestamp: float = Field(gt=0, allow_inf_nan=False)
    accuracy: float = Field(default=10, ge=0, le=200, allow_inf_nan=False)
    marked: bool = False


class CheckinResponse(BaseModel):
    """Only explicit runner responses may resolve or request escalation."""
    response: Literal["OK", "HELP"]


class LostItemInput(BaseModel):
    """Keep item labels bounded and outside the agent's instruction channel."""
    session_id: str
    item: str = Field(default="", max_length=100)


class DemoInput(BaseModel):
    """Both scripted scenarios feed the regular event-processing pipeline."""
    scenario: Literal["safety", "normal"] = "safety"


class HelperInput(BaseModel):
    """A helper explicitly supplies a discovery location and availability."""
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    available: bool = True
