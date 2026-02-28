from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class DiaryEntryRequest(BaseModel):
    text: Optional[str] = Field(None, description="Text entry")
    audio_data: Optional[str] = Field(None, description="Base64 encoded audio data")
    entry_type: str = Field(..., description="Type: 'food', 'mood', 'disease', or 'medication'")
    timestamp: Optional[datetime] = Field(None, description="Entry timestamp")


class DiaryEntryResponse(BaseModel):
    id: str
    text: str
    entry_type: str
    timestamp: datetime
    sentiment: Optional[str] = None
    summary: Optional[str] = None
    suggestions: List[str] = []


class DiarySummaryResponse(BaseModel):
    total_entries: int
    date_range: Dict[str, str]
    sentiment_trend: List[Dict[str, Any]]
    common_diseases: List[Dict[str, Any]]
    mood_patterns: List[Dict[str, Any]]
    suggestions: List[str]
    visualization_data: Dict[str, Any]


class ClinicalNoteRequest(BaseModel):
    audio_data: str = Field(..., description="Base64 encoded audio data")
    language: str = Field("en-US", description="Speech language code")


class SOAPNote(BaseModel):
    subjective: str = Field(..., description="Patient's subjective description")
    objective: str = Field(..., description="Objective observations and findings")
    assessment: str = Field(..., description="Clinical assessment and diagnosis")
    plan: str = Field(..., description="Treatment plan and next steps")


class ClinicalNoteResponse(BaseModel):
    transcription: str
    soap_note: SOAPNote
    health_entities: List[Dict[str, Any]]


class HealthEntity(BaseModel):
    text: str
    category: str
    confidence: float
    offset: int
    length: int


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
