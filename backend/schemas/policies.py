from pydantic import BaseModel


class NamedResource(BaseModel):
    name: str


class SizedResource(BaseModel):
    name: str
    size: str | None = None
    has_content: bool | None = None