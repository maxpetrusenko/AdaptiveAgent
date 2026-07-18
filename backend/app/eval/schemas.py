from pydantic import BaseModel, ConfigDict, Field


class EvalCaseCreate(BaseModel):
    name: str
    input: str
    expected_output: str
    tags: list[str] = Field(default_factory=list)
    source: str = "manual"


class EvalCaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    input: str
    expected_output: str
    tags: list[str]
    source: str
    created_at: str
