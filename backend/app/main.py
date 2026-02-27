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

import pathlib
try:
    backend_dir = pathlib.Path(__file__).parent.parent
    env_path = backend_dir / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)
        print(f"Loaded .env from: {env_path} (override=True)")
    else:
        load_dotenv(override=True)
        print("Loaded .env from current directory (override=True)")
except Exception as e:
    print(f"Warning: Error loading .env file: {e}")
    load_dotenv(override=True)

from starlette.requests import Request
from starlette.datastructures import UploadFile as StarletteUploadFile

app = FastAPI(
    title="Healthcare AI Assistant",
    description="AI-powered health diary summarizer and clinical note cleaner",
    version="1.0.0"
)

import starlette.requests
original_max_content_length = getattr(starlette.requests.Request, 'max_content_length', None)
starlette.requests.Request.max_content_length = 10 * 1024 * 1024

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

diary_entries: List[Dict[str, Any]] = []


@app.get("/")
async def root():
    return {
        "message": "Healthcare AI Assistant API",
        "endpoints": {
            "health_diary": "/api/diary",
            "clinical_notes": "/api/clinical/transcribe"
        }
    }


@app.get("/health")
async def health_check():
    try:
        speech_available = False
        openai_available = False
        text_analytics_available = False
        
        try:
            speech_available = azure_clients.speech_config is not None
        except Exception as e:
            print(f"Speech service check failed: {e}")
        
        try:
            client = azure_clients.openai_client
            openai_available = client is not None
            if not openai_available:
                print("OpenAI client is None - checking environment variables...")
                print(f"  Endpoint set: {bool(azure_clients.openai_endpoint)}")
                print(f"  API key set: {bool(azure_clients.openai_api_key)}")
        except Exception as e:
            print(f"OpenAI service check failed: {e}")
            import traceback
            traceback.print_exc()
            openai_available = False
        
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


@app.post("/api/diary/entry", response_model=DiaryEntryResponse)
async def create_diary_entry(
    text: str = Form(None),
    audio_data: str = Form(None),
    entry_type: str = Form(...),
    timestamp: str = Form(None)
):
    try:
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
        
        entry_timestamp = datetime.now()
        if timestamp:
            try:
                entry_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except:
                pass
        
        sentiment = diary_pipeline.analyze_sentiment(transcribed_text)
        
        entry_dict = {
            "id": str(uuid.uuid4()),
            "text": transcribed_text,
            "entry_type": entry_type,
            "timestamp": entry_timestamp,
            "sentiment": sentiment
        }
        
        suggestions = diary_pipeline._generate_suggestions([entry_dict])
        
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
    try:
        summary = diary_pipeline.generate_summary(diary_entries)
        return DiarySummaryResponse(**summary)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating summary: {str(e)}")


@app.delete("/api/diary/entries/{entry_id}")
async def delete_diary_entry(entry_id: str):
    global diary_entries
    original_count = len(diary_entries)
    diary_entries = [e for e in diary_entries if e["id"] != entry_id]
    
    if len(diary_entries) == original_count:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    return {"message": "Entry deleted successfully"}


@app.post("/api/clinical/transcribe", response_model=ClinicalNoteResponse)
async def transcribe_clinical_note(
    audio_data: str = Form(...),
    language: str = Form("en-US")
):
    try:
        audio_bytes = decode_audio_base64(audio_data)
        is_valid, msg = validate_audio_format(audio_bytes)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Invalid audio format: {msg}")
        
        transcription = azure_clients.transcribe_audio(audio_bytes, language=language)
        
        health_entities = {"entities": [], "relations": []}
        try:
            health_entities = azure_clients.extract_health_entities(transcription)
        except Exception as e:
            print(f"Health entity extraction failed: {str(e)}")
        
        soap_note_dict = soap_pipeline.generate_soap_note(transcription, health_entities)
        soap_note = SOAPNote(**soap_note_dict)
        
        return ClinicalNoteResponse(
            transcription=transcription,
            soap_note=soap_note,
            health_entities=health_entities.get("entities", [])
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing clinical note: {str(e)}")


@app.get("/test-openai")
async def test_openai():
    import sys
    import logging
    from openai import AzureOpenAI
    
    sys.stdout.flush()
    print("\n" + "="*50, flush=True)
    print("=== TESTING OPENAI CLIENT ===", flush=True)
    print("="*50, flush=True)
    sys.stdout.flush()
    
    try:
        endpoint = getattr(azure_clients, 'openai_endpoint', None)
        api_key = getattr(azure_clients, 'openai_api_key', None)
        deployment = getattr(azure_clients, 'openai_deployment', None)
        api_version = getattr(azure_clients, 'openai_api_version', None)
        
        debug_info = {
            "endpoint": endpoint,
            "api_key_present": bool(api_key),
            "api_key_length": len(api_key) if api_key else 0,
            "deployment": deployment,
            "api_version": api_version
        }
        
        print(f"Endpoint: {endpoint}")
        print(f"API Key present: {bool(api_key)}")
        if api_key:
            print(f"API Key length: {len(api_key)}")
        print(f"Deployment: {deployment}")
        print(f"API Version: {api_version}")
        
        if not endpoint:
            return {
                "status": "error",
                "message": "AZURE_OPENAI_ENDPOINT is not set",
                "debug": debug_info
            }
        
        if not api_key:
            return {
                "status": "error",
                "message": "AZURE_OPENAI_API_KEY is not set",
                "debug": debug_info
            }
        
        print("Attempting direct initialization...")
        endpoint_clean = endpoint.rstrip('/')
        
        try:
            test_client = AzureOpenAI(
                api_version=api_version,
                azure_endpoint=endpoint_clean,
                api_key=api_key
            )
            print("Direct initialization successful!")
            
            print("Making test API call...")
            response = test_client.chat.completions.create(
                model=deployment,
                messages=[{"role": "user", "content": "Say hello"}],
                max_tokens=10
            )
            
            return {
                "status": "success",
                "message": "OpenAI is working!",
                "test_response": response.choices[0].message.content,
                "debug": debug_info
            }
        except Exception as init_error:
            error_msg = str(init_error)
            error_type = type(init_error).__name__
            print(f"Initialization failed: {error_type}: {error_msg}")
            import traceback
            tb = traceback.format_exc()
            print(tb)
            
            return {
                "status": "error",
                "message": f"Failed to initialize OpenAI client: {error_msg}",
                "error_type": error_type,
                "traceback": tb,
                "debug": debug_info
            }
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"ERROR in test_openai: {error_detail}")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": str(e),
                "traceback": error_detail
            }
        )


@app.post("/api/clinical/text-to-soap", response_model=ClinicalNoteResponse)
async def text_to_soap(text: str = Form(...)):
    try:
        print(f"\n=== SOAP Generation Request ===")
        print(f"OpenAI client check: {azure_clients.openai_client is not None}")
        if not azure_clients.openai_client:
            print("WARNING: OpenAI client is None - will use fallback")
            print(f"Endpoint: {azure_clients.openai_endpoint}")
            print(f"API Key set: {bool(azure_clients.openai_api_key)}")
            print(f"Deployment: {azure_clients.openai_deployment}")
            print(f"API Version: {azure_clients.openai_api_version}")
        
        health_entities = {"entities": [], "relations": []}
        try:
            health_entities = azure_clients.extract_health_entities(text)
        except Exception as e:
            print(f"Health entity extraction failed: {str(e)}")
        
        soap_note_dict = soap_pipeline.generate_soap_note(text, health_entities)
        soap_note = SOAPNote(**soap_note_dict)
        
        return ClinicalNoteResponse(
            transcription=text,
            soap_note=soap_note,
            health_entities=health_entities.get("entities", [])
        )
    except Exception as e:
        print(f"ERROR in text_to_soap: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating SOAP note: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
