"""FastAPI main application with endpoints for health diary and clinical notes."""
import os
import uuid
from datetime import datetime
from typing import List, Dict, Any
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from .azure_clients import AzureClients
from .schemas import (
    DiaryEntryRequest, DiaryEntryResponse, DiarySummaryResponse,
    ClinicalNoteRequest, ClinicalNoteResponse, SOAPNote, ErrorResponse
)
from .pipeline import DiaryPipeline, SOAPPipeline
from .utils_audio import decode_audio_base64, validate_audio_format

# Load environment variables
# Try to load from backend directory first, then current directory
import pathlib
try:
    backend_dir = pathlib.Path(__file__).parent.parent
    env_path = backend_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"Loaded .env from: {env_path}")
    else:
        load_dotenv()  # Fallback to current directory
        print("Loaded .env from current directory")
except Exception as e:
    print(f"Warning: Error loading .env file: {e}")
    load_dotenv()  # Try fallback

# Initialize FastAPI app with increased body size limit
from starlette.requests import Request
from starlette.datastructures import UploadFile as StarletteUploadFile

app = FastAPI(
    title="Healthcare AI Assistant",
    description="AI-powered health diary summarizer and clinical note cleaner",
    version="1.0.0"
)

# Increase request body size limit (Starlette default is 1MB)
# Patch the default max_content_length
import starlette.requests
original_max_content_length = getattr(starlette.requests.Request, 'max_content_length', None)
starlette.requests.Request.max_content_length = 10 * 1024 * 1024  # 10MB

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Azure clients and pipelines
try:
    azure_clients = AzureClients()
    diary_pipeline = DiaryPipeline(azure_clients)
    soap_pipeline = SOAPPipeline(azure_clients)
    print("Azure clients initialized successfully")
except Exception as e:
    print(f"Error initializing Azure clients: {e}")
    import traceback
    traceback.print_exc()
    raise

# In-memory storage (in production, use a database)
diary_entries: List[Dict[str, Any]] = []


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Healthcare AI Assistant API",
        "endpoints": {
            "health_diary": "/api/diary",
            "clinical_notes": "/api/clinical/transcribe"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        # Safely check service availability
        speech_available = False
        openai_available = False
        text_analytics_available = False
        
        try:
            speech_available = azure_clients.speech_config is not None
        except Exception as e:
            print(f"Speech service check failed: {e}")
        
        try:
            openai_available = azure_clients.openai_client is not None
        except Exception as e:
            print(f"OpenAI service check failed: {e}")
        
        try:
            text_analytics_available = azure_clients.text_analytics_client is not None
        except Exception as e:
            print(f"Text Analytics service check failed: {e}")
        
        return {
            "status": "healthy", 
            "services": {
                "speech": speech_available,
                "openai": openai_available,
                "text_analytics": text_analytics_available
            },
            "debug": {
                "speech_key_set": bool(azure_clients.speech_key),
                "speech_region": azure_clients.speech_region,
                "openai_endpoint_set": bool(azure_clients.openai_endpoint),
                "openai_api_key_set": bool(azure_clients.openai_api_key),
                "openai_endpoint": azure_clients.openai_endpoint if azure_clients.openai_endpoint else None,
                "text_analytics_endpoint_set": bool(azure_clients.text_analytics_endpoint)
            }
        }
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"Health check error: {error_detail}")
        return {
            "status": "error",
            "error": str(e),
            "debug": {
                "speech_key_set": bool(getattr(azure_clients, 'speech_key', None)),
                "speech_region": getattr(azure_clients, 'speech_region', 'unknown'),
            }
        }


# ==================== Health Diary Endpoints ====================

@app.post("/api/diary/entry", response_model=DiaryEntryResponse)
async def create_diary_entry(
    text: str = Form(None),
    audio_data: str = Form(None),
    entry_type: str = Form(...),
    timestamp: str = Form(None)
):
    """Create a new health diary entry from text or audio."""
    try:
        # Process audio if provided
        transcribed_text = text
        if audio_data and not text:
            try:
                audio_bytes = decode_audio_base64(audio_data)
                is_valid, msg = validate_audio_format(audio_bytes)
                if not is_valid:
                    raise HTTPException(status_code=400, detail=f"Invalid audio format: {msg}")
                
                transcribed_text = azure_clients.transcribe_audio(audio_bytes)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Audio transcription failed: {str(e)}")
        
        if not transcribed_text:
            raise HTTPException(status_code=400, detail="Either text or audio_data must be provided")
        
        # Parse timestamp
        entry_timestamp = datetime.now()
        if timestamp:
            try:
                entry_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except:
                pass
        
        # Analyze sentiment
        sentiment = diary_pipeline.analyze_sentiment(transcribed_text)
        
        # Generate suggestions
        entry_dict = {
            "id": str(uuid.uuid4()),
            "text": transcribed_text,
            "entry_type": entry_type,
            "timestamp": entry_timestamp,
            "sentiment": sentiment
        }
        
        # Generate entry-specific suggestions
        suggestions = diary_pipeline._generate_suggestions([entry_dict])
        
        # Store entry
        diary_entries.append(entry_dict)
        
        return DiaryEntryResponse(
            id=entry_dict["id"],
            text=transcribed_text,
            entry_type=entry_type,
            timestamp=entry_timestamp,
            sentiment=sentiment,
            summary=None,
            suggestions=suggestions
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating diary entry: {str(e)}")


@app.get("/api/diary/entries", response_model=List[DiaryEntryResponse])
async def get_diary_entries():
    """Get all diary entries."""
    return [
        DiaryEntryResponse(
            id=entry["id"],
            text=entry["text"],
            entry_type=entry["entry_type"],
            timestamp=entry["timestamp"],
            sentiment=entry.get("sentiment"),
            summary=None,
            suggestions=[]
        )
        for entry in diary_entries
    ]


@app.get("/api/diary/summary", response_model=DiarySummaryResponse)
async def get_diary_summary():
    """Get summary and trends from all diary entries."""
    try:
        summary = diary_pipeline.generate_summary(diary_entries)
        return DiarySummaryResponse(**summary)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating summary: {str(e)}")


@app.delete("/api/diary/entries/{entry_id}")
async def delete_diary_entry(entry_id: str):
    """Delete a diary entry."""
    global diary_entries
    original_count = len(diary_entries)
    diary_entries = [e for e in diary_entries if e["id"] != entry_id]
    
    if len(diary_entries) == original_count:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    return {"message": "Entry deleted successfully"}


# ==================== Clinical Notes Endpoints ====================

@app.post("/api/clinical/transcribe", response_model=ClinicalNoteResponse)
async def transcribe_clinical_note(
    audio_data: str = Form(...),
    language: str = Form("en-US")
):
    """Transcribe clinical voice note and generate SOAP format."""
    try:
        # Decode and validate audio
        audio_bytes = decode_audio_base64(audio_data)
        is_valid, msg = validate_audio_format(audio_bytes)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Invalid audio format: {msg}")
        
        # Transcribe audio
        transcription = azure_clients.transcribe_audio(audio_bytes, language=language)
        
        # Extract health entities
        health_entities = {"entities": [], "relations": []}
        try:
            health_entities = azure_clients.extract_health_entities(transcription)
        except Exception as e:
            # Continue even if entity extraction fails
            print(f"Health entity extraction failed: {str(e)}")
        
        # Generate SOAP note
        soap_note_dict = soap_pipeline.generate_soap_note(transcription, health_entities)
        soap_note = SOAPNote(**soap_note_dict)
        
        # Calculate confidence (simplified)
        confidence = 0.85  # In production, use actual confidence from transcription
        
        return ClinicalNoteResponse(
            transcription=transcription,
            soap_note=soap_note,
            health_entities=health_entities.get("entities", []),
            confidence_score=confidence
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing clinical note: {str(e)}")


@app.post("/api/clinical/text-to-soap", response_model=ClinicalNoteResponse)
async def text_to_soap(text: str = Form(...)):
    """Convert text dictation directly to SOAP format."""
    try:
        # Extract health entities
        health_entities = {"entities": [], "relations": []}
        try:
            health_entities = azure_clients.extract_health_entities(text)
        except Exception as e:
            print(f"Health entity extraction failed: {str(e)}")
        
        # Generate SOAP note
        soap_note_dict = soap_pipeline.generate_soap_note(text, health_entities)
        soap_note = SOAPNote(**soap_note_dict)
        
        return ClinicalNoteResponse(
            transcription=text,
            soap_note=soap_note,
            health_entities=health_entities.get("entities", []),
            confidence_score=1.0
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating SOAP note: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
