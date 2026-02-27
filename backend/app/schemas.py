"""Pydantic schemas for request/response models."""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class DiaryEntryRequest(BaseModel):
    """Request schema for health diary entry."""
    text: Optional[str] = Field(None, description="Text entry")
    audio_data: Optional[str] = Field(None, description="Base64 encoded audio data")
    entry_type: str = Field(..., description="Type: 'symptom', 'food', 'mood', or 'general'")
    timestamp: Optional[datetime] = Field(None, description="Entry timestamp")


class DiaryEntryResponse(BaseModel):
    """Response schema for diary entry."""
    id: str
    text: str
    entry_type: str
    timestamp: datetime
    sentiment: Optional[str] = None
    summary: Optional[str] = None
    suggestions: List[str] = []


class DiarySummaryResponse(BaseModel):
    """Response schema for diary summary."""
    total_entries: int
    date_range: Dict[str, str]
    sentiment_trend: List[Dict[str, Any]]
    common_symptoms: List[Dict[str, int]]
    mood_patterns: List[Dict[str, Any]]
    suggestions: List[str]
    visualization_data: Dict[str, Any]


class ClinicalNoteRequest(BaseModel):
    """Request schema for clinical note transcription."""
    audio_data: str = Field(..., description="Base64 encoded audio data")
    language: str = Field("en-US", description="Speech language code")


class SOAPNote(BaseModel):
    """SOAP format structured note."""
    subjective: str = Field(..., description="Patient's subjective description")
    objective: str = Field(..., description="Objective observations and findings")
    assessment: str = Field(..., description="Clinical assessment and diagnosis")
    plan: str = Field(..., description="Treatment plan and next steps")


class ClinicalNoteResponse(BaseModel):
    """Response schema for clinical note."""
    transcription: str
    soap_note: SOAPNote
    health_entities: List[Dict[str, Any]]
    confidence_score: float


class HealthEntity(BaseModel):
    """Health entity extracted from text."""
    text: str
    category: str
    confidence: float
    offset: int
    length: int


class ErrorResponse(BaseModel):
    """Error response schema."""
    error: str
    detail: Optional[str] = None
