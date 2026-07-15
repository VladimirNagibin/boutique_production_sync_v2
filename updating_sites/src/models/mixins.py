from pydantic import BaseModel, UUID4


class IdMixin(BaseModel):
    id: UUID4
