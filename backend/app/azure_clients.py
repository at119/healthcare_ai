"""Azure service clients for Speech, OpenAI, and Text Analytics."""
import os
from typing import Optional
import azure.cognitiveservices.speech as speechsdk
from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from openai import AzureOpenAI


class AzureClients:
    """Manages Azure service clients."""
    
    def __init__(self):
        # Azure Speech Service
        self.speech_key = os.getenv("AZURE_SPEECH_KEY")
        self.speech_region = os.getenv("AZURE_SPEECH_REGION", "eastus")
        
        # Debug: Check if keys are loaded (only log if missing)
        if not self.speech_key:
            print("WARNING: AZURE_SPEECH_KEY not found in environment variables")
        
        # Azure OpenAI
        self.openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.openai_api_key = os.getenv("AZURE_OPENAI_API_KEY")
        self.openai_api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
        self.openai_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4")
        
        # Debug: Check if OpenAI keys are loaded
        if not self.openai_api_key:
            print("WARNING: AZURE_OPENAI_API_KEY not found in environment variables")
        if not self.openai_endpoint:
            print("WARNING: AZURE_OPENAI_ENDPOINT not found in environment variables")
        
        # Text Analytics for Health
        self.text_analytics_endpoint = os.getenv("AZURE_TEXT_ANALYTICS_ENDPOINT")
        self.text_analytics_key = os.getenv("AZURE_TEXT_ANALYTICS_KEY")
        
        # Initialize clients
        self._speech_config = None
        self._openai_client = None
        self._text_analytics_client = None
    
    @property
    def speech_config(self) -> Optional[speechsdk.SpeechConfig]:
        """Get Azure Speech configuration."""
        try:
            if not self._speech_config and self.speech_key:
                self._speech_config = speechsdk.SpeechConfig(
                    subscription=self.speech_key,
                    region=self.speech_region
                )
            return self._speech_config
        except Exception as e:
            print(f"Error creating Speech config: {e}")
            return None
    
    @property
    def openai_client(self) -> Optional[AzureOpenAI]:
        """Get Azure OpenAI client."""
        try:
            if not self._openai_client and self.openai_endpoint and self.openai_api_key:
                self._openai_client = AzureOpenAI(
                    api_key=self.openai_api_key,
                    api_version=self.openai_api_version,
                    azure_endpoint=self.openai_endpoint
                )
            return self._openai_client
        except Exception as e:
            print(f"Error creating OpenAI client: {e}")
            return None
    
    @property
    def text_analytics_client(self) -> Optional[TextAnalyticsClient]:
        """Get Text Analytics client."""
        if not self._text_analytics_client and self.text_analytics_endpoint and self.text_analytics_key:
            credential = AzureKeyCredential(self.text_analytics_key)
            self._text_analytics_client = TextAnalyticsClient(
                endpoint=self.text_analytics_endpoint,
                credential=credential
            )
        return self._text_analytics_client
    
    def transcribe_audio(self, audio_data: bytes, language: str = "en-US") -> str:
        """Transcribe audio to text using Azure Speech-to-Text."""
        if not self.speech_config:
            raise ValueError("Azure Speech service not configured")
        
        if len(audio_data) < 1000:  # Very small audio file
            raise ValueError("Audio file is too short. Please record at least 1-2 seconds of audio.")
        
        import io
        import wave
        
        # Try to read WAV file to get actual format
        sample_rate = 16000
        channels = 1
        bits_per_sample = 16
        
        try:
            audio_io = io.BytesIO(audio_data)
            with wave.open(audio_io, 'rb') as wav_file:
                sample_rate = wav_file.getframerate()
                channels = wav_file.getnchannels()
                bits_per_sample = wav_file.getsampwidth() * 8
                frames = wav_file.getnframes()
                print(f"WAV file detected: {sample_rate}Hz, {channels} channel(s), {bits_per_sample}bit, {frames} frames")
                
                # Read the actual audio data
                audio_io.seek(0)
                audio_data = audio_io.read()
        except Exception as e:
            print(f"Not a standard WAV file or error reading: {e}")
            # Assume it's raw PCM or try to process anyway
            pass
        
        # Create audio stream format matching the actual audio
        try:
            stream_format = speechsdk.audio.AudioStreamFormat(
                samples_per_second=sample_rate,
                bits_per_sample=bits_per_sample,
                channels=channels
            )
        except Exception as e:
            print(f"Error creating stream format: {e}, using defaults")
            # Fallback to default format
            stream_format = speechsdk.audio.AudioStreamFormat(
                samples_per_second=16000,
                bits_per_sample=16,
                channels=1
            )
        
        # Create push stream
        push_stream = speechsdk.audio.PushAudioInputStream(stream_format=stream_format)
        
        # For WAV files, we need to extract just the PCM data (skip header)
        # But only if we detected it's a WAV file
        pcm_data = audio_data
        if audio_data[:4] == b'RIFF' and audio_data[8:12] == b'WAVE':
            try:
                # Parse WAV file to extract PCM data
                audio_io = io.BytesIO(audio_data)
                with wave.open(audio_io, 'rb') as wav_file:
                    # Read all frames (this gives us the raw PCM data)
                    pcm_data = wav_file.readframes(wav_file.getnframes())
                    print(f"Extracted {len(pcm_data)} bytes of PCM data from WAV file")
            except Exception as e:
                print(f"Error extracting PCM from WAV: {e}, using raw data")
                # If we can't parse it, try using the whole file
                pcm_data = audio_data
        else:
            # Not a WAV file, use as-is (might be raw PCM)
            pcm_data = audio_data
        
        # Write audio data in chunks
        chunk_size = 4096
        audio_io = io.BytesIO(pcm_data)
        bytes_written = 0
        while True:
            chunk = audio_io.read(chunk_size)
            if not chunk:
                break
            push_stream.write(chunk)
            bytes_written += len(chunk)
        
        print(f"Wrote {bytes_written} bytes to audio stream")
        push_stream.close()
        
        # Create audio config
        audio_config = speechsdk.audio.AudioConfig(stream=push_stream)
        
        # Create recognizer
        recognizer = speechsdk.SpeechRecognizer(
            speech_config=self.speech_config,
            audio_config=audio_config,
            language=language
        )
        
        # Perform recognition
        print("Starting speech recognition...")
        result = recognizer.recognize_once_async().get()
        print(f"Recognition result reason: {result.reason}")
        
        if result.reason == speechsdk.ResultReason.RecognizedSpeech:
            text = result.text.strip()
            if not text:
                raise ValueError("Speech was recognized but no text was returned. Please try speaking more clearly.")
            print(f"Recognized text: {text}")
            return text
        elif result.reason == speechsdk.ResultReason.NoMatch:
            no_match_details = speechsdk.NoMatchDetails(result)
            error_msg = (
                "No speech could be recognized. Please try:\n"
                "- Speaking clearly and loudly\n"
                "- Recording for at least 2-3 seconds\n"
                "- Ensuring your microphone is working\n"
                "- Reducing background noise\n"
                f"Reason: {no_match_details.reason}"
            )
            raise ValueError(error_msg)
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation = speechsdk.CancellationDetails(result)
            error_msg = f"Speech recognition canceled: {cancellation.reason}"
            if cancellation.reason == speechsdk.CancellationReason.Error:
                error_msg += f"\nError details: {cancellation.error_details}"
            raise ValueError(error_msg)
        else:
            raise ValueError(f"Speech recognition failed with reason: {result.reason}")
    
    def extract_health_entities(self, text: str) -> dict:
        """Extract health-related entities using Text Analytics for Health."""
        if not self.text_analytics_client:
            raise ValueError("Text Analytics service not configured")
        
        documents = [text]
        result = self.text_analytics_client.analyze_healthcare_entities(documents)
        
        docs = [doc for doc in result if not doc.is_error]
        if not docs:
            return {"entities": [], "relations": []}
        
        doc_result = docs[0]
        entities = []
        for entity in doc_result.entities:
            entities.append({
                "text": entity.text,
                "category": entity.category,
                "confidence": entity.confidence_score,
                "offset": entity.offset,
                "length": entity.length
            })
        
        relations = []
        for relation in doc_result.entity_relations:
            relations.append({
                "relation_type": relation.relation_type,
                "roles": [
                    {
                        "entity": role.entity.text,
                        "name": role.name
                    }
                    for role in relation.roles
                ]
            })
        
        return {"entities": entities, "relations": relations}
