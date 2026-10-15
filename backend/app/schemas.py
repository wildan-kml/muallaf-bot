import re

from pydantic import BaseModel, Field, field_validator


SESSION_ID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"


def _plain_text(value: str) -> str:
    cleaned = value.strip()
    if any(ord(character) < 32 and character not in "\t\n\r" for character in cleaned):
        raise ValueError("Teks mengandung karakter yang tidak diizinkan")
    return cleaned


class ChatSource(BaseModel):
    document_title: str
    page_number: int | None = None
    reference_label: str | None = None
    content_preview: str = ""
    file_name: str | None = None
    chunk_id: str | None = None
    source_id: str | None = None
    source_type: str | None = None
    category: str | None = None
    verified_at: str | None = None
    last_checked: str | None = None
    verification_status: str | None = None
    similarity_score: float | None = None


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|bot)$")
    text: str = Field(..., min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    question: str | None = Field(default=None, max_length=1000)
    message: str | None = Field(default=None, max_length=1000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=6)
    session_id: str | None = Field(default=None, max_length=36, pattern=SESSION_ID_PATTERN)

    @property
    def prompt(self) -> str:
        return (self.question or self.message or "").strip()


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource] = Field(default_factory=list)
    mode: str = "rag"
    reply: str | None = None
    next_actions: list[str] = Field(default_factory=list)
    predicted_intent: str | None = None
    confidence: float | None = None
    retrieval_confidence: float | None = None
    model_status: str | None = None
    source: str | None = None
    kb_id: str | None = None
    escalation: str | None = None
    session_id: str | None = None


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(..., min_length=1, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict[str, str]


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")
    display_name: str = Field(..., min_length=2, max_length=120)
    password: str = Field(..., min_length=10, max_length=128)
    privacy_accepted: bool

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        value = _plain_text(value)
        if re.search(r"[\r\n\t]", value):
            raise ValueError("Nama lengkap harus ditulis dalam satu baris")
        return value


class AccountUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    current_password: str | None = Field(default=None, min_length=1, max_length=128)
    new_password: str | None = Field(default=None, min_length=10, max_length=128)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = _plain_text(value)
        if re.search(r"[\r\n\t]", value):
            raise ValueError("Nama lengkap harus ditulis dalam satu baris")
        return value


class SessionCreateRequest(BaseModel):
    title: str = Field(default="Percakapan baru", max_length=160)


class SessionResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    expires_at: str


class StoredMessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    created_at: str
    metadata: dict = Field(default_factory=dict)


class ContactRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=5, max_length=160)
    subject: str = Field(..., min_length=2, max_length=160)
    message: str = Field(..., min_length=5, max_length=2000)


class ContactResponse(BaseModel):
    status: str
    message: str


class FeedbackRequest(BaseModel):
    identity: str | None = Field(default=None, max_length=120)
    email: str = Field(..., min_length=5, max_length=160, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    feedback: str = Field(..., min_length=3, max_length=5000)


class FeedbackResponse(BaseModel):
    status: str
    message: str
