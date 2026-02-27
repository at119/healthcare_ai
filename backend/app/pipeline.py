"""Processing pipelines for diary summarization and SOAP note generation."""
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from .azure_clients import AzureClients


class DiaryPipeline:
    """Pipeline for processing health diary entries."""
    
    def __init__(self, azure_clients: AzureClients):
        self.azure_clients = azure_clients
    
    def analyze_sentiment(self, text: str) -> str:
        """Analyze sentiment of diary entry."""
        if not self.azure_clients.openai_client:
            return "neutral"
        
        try:
            response = self.azure_clients.openai_client.chat.completions.create(
                model=self.azure_clients.openai_deployment,
                messages=[
                    {"role": "system", "content": "You are a sentiment analyzer. Respond with only one word: 'positive', 'negative', or 'neutral'."},
                    {"role": "user", "content": f"Analyze the sentiment of this health diary entry: {text}"}
                ],
                temperature=0.3,
                max_tokens=10
            )
            sentiment = response.choices[0].message.content.strip().lower()
            if sentiment not in ["positive", "negative", "neutral"]:
                return "neutral"
            return sentiment
        except:
            return "neutral"
    
    def generate_summary(self, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate summary from multiple diary entries."""
        if not entries:
            return {
                "total_entries": 0,
                "date_range": {},
                "sentiment_trend": [],
                "common_symptoms": [],
                "mood_patterns": [],
                "suggestions": [],
                "visualization_data": {}
            }
        
        # Extract dates and sentiments
        dates = [entry.get("timestamp", datetime.now()) for entry in entries]
        sentiments = [entry.get("sentiment", "neutral") for entry in entries]
        
        # Count symptoms and moods
        symptoms = {}
        moods = {}
        for entry in entries:
            if entry.get("entry_type") == "symptom":
                text = entry.get("text", "").lower()
                # Simple keyword extraction
                common_symptoms = ["headache", "pain", "fever", "nausea", "fatigue", "cough", "sore throat"]
                for symptom in common_symptoms:
                    if symptom in text:
                        symptoms[symptom] = symptoms.get(symptom, 0) + 1
            
            if entry.get("entry_type") == "mood":
                mood_text = entry.get("text", "").lower()
                if "happy" in mood_text or "good" in mood_text:
                    moods["positive"] = moods.get("positive", 0) + 1
                elif "sad" in mood_text or "bad" in mood_text:
                    moods["negative"] = moods.get("negative", 0) + 1
                else:
                    moods["neutral"] = moods.get("neutral", 0) + 1
        
        # Generate suggestions using AI
        suggestions = self._generate_suggestions(entries)
        
        # Prepare visualization data
        sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}
        for sentiment in sentiments:
            sentiment_counts[sentiment] = sentiment_counts.get(sentiment, 0) + 1
        
        # Time series data for visualization
        time_series = []
        for i, entry in enumerate(entries):
            time_series.append({
                "date": entry.get("timestamp", datetime.now()).isoformat(),
                "sentiment": entry.get("sentiment", "neutral"),
                "type": entry.get("entry_type", "general")
            })
        
        return {
            "total_entries": len(entries),
            "date_range": {
                "start": min(dates).isoformat() if dates else datetime.now().isoformat(),
                "end": max(dates).isoformat() if dates else datetime.now().isoformat()
            },
            "sentiment_trend": [
                {"sentiment": k, "count": v} for k, v in sentiment_counts.items()
            ],
            "common_symptoms": [
                {"symptom": k, "count": v} for k, v in sorted(symptoms.items(), key=lambda x: x[1], reverse=True)[:5]
            ],
            "mood_patterns": [
                {"mood": k, "count": v} for k, v in moods.items()
            ],
            "suggestions": suggestions,
            "visualization_data": {
                "time_series": time_series,
                "sentiment_distribution": sentiment_counts
            }
        }
    
    def _generate_suggestions(self, entries: List[Dict[str, Any]]) -> List[str]:
        """Generate AI-powered suggestions based on diary entries."""
        if not self.azure_clients.openai_client or not entries:
            return []
        
        try:
            # Get recent entries
            recent_entries = entries[-10:] if len(entries) > 10 else entries
            entries_text = "\n".join([
                f"{entry.get('entry_type', 'general')}: {entry.get('text', '')}"
                for entry in recent_entries
            ])
            
            response = self.azure_clients.openai_client.chat.completions.create(
                model=self.azure_clients.openai_deployment,
                messages=[
                    {"role": "system", "content": "You are a health assistant. Provide 2-3 gentle, actionable suggestions based on health diary entries. Be supportive and professional. Format as a simple list."},
                    {"role": "user", "content": f"Based on these diary entries, provide suggestions:\n{entries_text}"}
                ],
                temperature=0.7,
                max_tokens=200
            )
            
            suggestions_text = response.choices[0].message.content.strip()
            # Parse suggestions (split by newlines or bullets)
            suggestions = [
                s.strip().lstrip("- ").lstrip("* ")
                for s in suggestions_text.split("\n")
                if s.strip()
            ]
            return suggestions[:3]  # Limit to 3 suggestions
        except:
            return ["Consider maintaining regular sleep patterns", "Stay hydrated throughout the day"]


class SOAPPipeline:
    """Pipeline for generating SOAP notes from clinical dictation."""
    
    def __init__(self, azure_clients: AzureClients):
        self.azure_clients = azure_clients
    
    def generate_soap_note(self, transcription: str, health_entities: Optional[Dict] = None) -> Dict[str, str]:
        """Generate structured SOAP note from transcription."""
        if not self.azure_clients.openai_client:
            # Fallback: simple parsing
            return {
                "subjective": transcription,
                "objective": "No objective findings recorded.",
                "assessment": "Assessment pending review.",
                "plan": "Plan to be determined."
            }
        
        try:
            # Build context with health entities if available
            context = transcription
            if health_entities and health_entities.get("entities"):
                entities_text = ", ".join([
                    f"{e['text']} ({e['category']})"
                    for e in health_entities["entities"][:10]
                ])
                context += f"\n\nExtracted medical entities: {entities_text}"
            
            response = self.azure_clients.openai_client.chat.completions.create(
                model=self.azure_clients.openai_deployment,
                messages=[
                    {"role": "system", "content": """You are a medical documentation assistant. Transform clinical dictation into a structured SOAP note format.

SOAP Format:
- Subjective (S): Patient's description of symptoms, history, concerns
- Objective (O): Observable findings, vital signs, examination results, test results
- Assessment (A): Clinical impression, diagnosis, differential diagnosis
- Plan (P): Treatment plan, medications, follow-up, patient education

Be precise, professional, and maintain medical accuracy. If information is missing, indicate that clearly."""},
                    {"role": "user", "content": f"Convert this clinical dictation into SOAP format:\n\n{context}"}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            soap_text = response.choices[0].message.content.strip()
            
            # Parse SOAP sections
            soap_note = self._parse_soap_response(soap_text)
            return soap_note
        except Exception as e:
            # Fallback
            return {
                "subjective": transcription,
                "objective": "Objective findings to be documented.",
                "assessment": "Clinical assessment pending.",
                "plan": "Treatment plan to be determined."
            }
    
    def _parse_soap_response(self, soap_text: str) -> Dict[str, str]:
        """Parse AI response into SOAP sections."""
        sections = {
            "subjective": "",
            "objective": "",
            "assessment": "",
            "plan": ""
        }
        
        # Try to extract sections by headers
        text_lower = soap_text.lower()
        
        # Find section boundaries
        section_keywords = {
            "subjective": ["subjective", "s:", "chief complaint", "history of present illness"],
            "objective": ["objective", "o:", "physical examination", "vital signs", "exam"],
            "assessment": ["assessment", "a:", "impression", "diagnosis", "clinical assessment"],
            "plan": ["plan", "p:", "treatment", "follow-up", "management"]
        }
        
        lines = soap_text.split("\n")
        current_section = None
        
        for line in lines:
            line_lower = line.lower().strip()
            
            # Check if this line starts a new section
            for section, keywords in section_keywords.items():
                if any(line_lower.startswith(kw) or kw in line_lower[:20] for kw in keywords):
                    current_section = section
                    # Remove the header from the line
                    for kw in keywords:
                        if kw in line_lower:
                            line = line[line_lower.find(kw) + len(kw):].strip().lstrip(":").strip()
                            break
                    break
            
            if current_section and line.strip():
                if sections[current_section]:
                    sections[current_section] += " "
                sections[current_section] += line.strip()
        
        # If parsing failed, distribute content
        if not any(sections.values()):
            # Simple fallback: split by paragraphs
            paragraphs = [p.strip() for p in soap_text.split("\n\n") if p.strip()]
            if len(paragraphs) >= 4:
                sections["subjective"] = paragraphs[0]
                sections["objective"] = paragraphs[1]
                sections["assessment"] = paragraphs[2]
                sections["plan"] = paragraphs[3]
            else:
                sections["subjective"] = soap_text
        
        # Ensure all sections have content
        for section in sections:
            if not sections[section]:
                sections[section] = f"{section.capitalize()} information to be documented."
        
        return sections
