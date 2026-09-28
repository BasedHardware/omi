from typing import Dict, Any, Optional, Union
from datetime import datetime
from pydantic import BaseModel, validator, ValidationError
from fastapi import HTTPException

class DailySummaryInput(BaseModel):
    uid: str
    summary_id: str
    date: str
    client_device_id: str
    summary_data: Optional[Dict[str, Any]] = None
    counters: Optional[Dict[str, Union[int, float]]] = None

    @validator('uid')
    def _clean_uid(cls, v: str) -> str:
        if not v or not isinstance(v, str):
            raise ValueError('uid must be a non-empty string')
        return v.strip()

    @validator('summary_id')
    def _clean_id(cls, v: str) -> str:
        if not v or not isinstance(v, str):
            raise ValueError('summary_id must be a non-empty string')
        return v.strip()

    @validator('date')
    def _clean_date(cls, v: str) -> str:
        try:
            datetime.strptime(v, '%Y-%m-%d')
        except ValueError:
            raise ValueError('date must be in YYYY-MM-DD format')
        return v

    @validator('client_device_id')
    def _clean_device_id(cls, v: str) -> str:
        if not v or not isinstance(v, str):
            raise ValueError('client_device_id must be a non-empty string')
        return v.strip()

    @validator('summary_data')
    def _validate_summary_data(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if v is not None and not isinstance(v, dict):
            raise ValueError('summary_data must be a dictionary or None')
        return v

    @validator('counters')
    def _validate_counters(cls, v: Optional[Dict[str, Union[int, float]]]) -> Optional[Dict[str, Union[int, float]]]:
        if v is not None:
            for key, value in v.items():
                if not isinstance(value, (int, float)):
                    raise ValueError(f'counters[{key}] must be int or float')
        return v

class PaginationInput(BaseModel):
    limit: int = 10
    offset: int = 0

    @validator('limit')
    def _validate_limit(cls, v: int) -> int:
        if not 1 <= v <= 100:
            raise ValueError('limit must be between 1 and 100')
        return v

    @validator('offset')
    def _validate_offset(cls, v: int) -> int:
        if v < 0:
            raise ValueError('offset must be >= 0')
        return v

def validate_daily_summary_input(**kwargs) -> DailySummaryInput:
    try:
        return DailySummaryInput(**kwargs)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

def validate_pagination_input(**kwargs) -> PaginationInput:
    try:
        return PaginationInput(**kwargs)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
