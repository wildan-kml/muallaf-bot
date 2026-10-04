from pydantic import BaseModel, Field


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
    history: list[ChatMessage] = Field(default_factory=list)

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


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=100)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict[str, str]


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
