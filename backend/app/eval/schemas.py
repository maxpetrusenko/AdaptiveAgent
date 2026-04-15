from pydantic import BaseModel


class EvalCaseCreate(BaseModel):
    name: str
    input: str
    expected_output: str
    tags: list[str] = []
    source: str = "manual"


class EvalCaseResponse(BaseModel):
    id: str
    name: str
    input: str
    expected_output: str
    tags: list[str]
    source: str
    created_at: str

    class Config:
        from_attributes = True
