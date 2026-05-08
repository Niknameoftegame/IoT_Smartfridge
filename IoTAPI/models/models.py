from pydantic import BaseModel
from datetime import date

class Content(BaseModel):
    expiration_date: date
    name: str

