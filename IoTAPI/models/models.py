from pydantic import BaseModel
from datetime import date

class Content(BaseModel):
    name: str
    expiration_date: date

