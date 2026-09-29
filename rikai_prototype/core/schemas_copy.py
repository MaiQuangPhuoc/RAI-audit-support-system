from pydantic import BaseModel, Field
from typing import List, Optional, Literal


class ColumnSchema(BaseModel):
    name: str = Field(description="Tên của cột")
    position: int = Field(description="Vị trí của cột, bắt đầu từ 1")
    description: Optional[str] = Field(
        default=None,
        description="Ý nghĩa của cột nếu có thể xác định"
    )


class TableSchema(BaseModel):
    type: Literal["table"] = "table"
    columns: List[ColumnSchema]


class SheetSchema(BaseModel):
    type: Literal["sheet"] = "sheet"
    name: Optional[str] = None
    columns: List[ColumnSchema]


class InputSchema(BaseModel):
    type: Literal["table", "sheet", "unknown"]
    sheet: Optional[str] = None
    columns: List[ColumnSchema] = []    