from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from .azure_clients import AzureClients


class DiaryPipeline:
    
    def __init__(self, azure_clients: AzureClients):
        self.azure_clients = azure_clients
    
    def analyze_sentiment(self, text: str) -> str:
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
        
        dates = [entry.get("timestamp", datetime.now()) for entry in entries]
        sentiments = [entry.get("sentiment", "neutral") for entry in entries]
        
        diseases = {}
        moods = {}
        for entry in entries:
            if entry.get("entry_type") == "disease":
                text = entry.get("text", "").lower()
                common_diseases = ["diabetes", "hypertension", "asthma", "arthritis", "heart disease", "cancer", "thyroid", "copd", "depression", "anxiety"]
                for disease in common_diseases:
                    if disease in text:
                        diseases[disease] = diseases.get(disease, 0) + 1
            
            if entry.get("entry_type") == "mood":
                mood_text = entry.get("text", "").lower()
                if "happy" in mood_text or "good" in mood_text:
                    moods["positive"] = moods.get("positive", 0) + 1
                elif "sad" in mood_text or "bad" in mood_text:
                    moods["negative"] = moods.get("negative", 0) + 1
                else:
                    moods["neutral"] = moods.get("neutral", 0) + 1
        
        suggestions = self._generate_suggestions(entries)
        
        sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}
        for sentiment in sentiments:
            sentiment_counts[sentiment] = sentiment_counts.get(sentiment, 0) + 1
        
        time_series = []
        for i, entry in enumerate(entries):
            time_series.append({
                "date": entry.get("timestamp", datetime.now()).isoformat(),
                "sentiment": entry.get("sentiment", "neutral"),
                "type": entry.get("entry_type", "food")
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
            "common_diseases": [
                {"disease": k, "count": v} for k, v in sorted(diseases.items(), key=lambda x: x[1], reverse=True)[:5]
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
        if not self.azure_clients.openai_client or not entries:
            return []
        
        try:
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
            suggestions = [
                s.strip().lstrip("- ").lstrip("* ")
                for s in suggestions_text.split("\n")
                if s.strip()
            ]
            return suggestions[:3]
        except:
            return ["Consider maintaining regular sleep patterns", "Stay hydrated throughout the day"]


class SOAPPipeline:
    
    def __init__(self, azure_clients: AzureClients):
        self.azure_clients = azure_clients
    
    def generate_soap_note(self, transcription: str, health_entities: Optional[Dict] = None, diary_entries: Optional[List[Dict]] = None) -> Dict[str, str]:
        if not self.azure_clients.openai_client:
            print("WARNING: OpenAI client not available, using fallback SOAP generation")
            return self._generate_fallback_soap(transcription, health_entities)
        
        try:
            context = transcription
            entities_context = ""
            if health_entities and health_entities.get("entities"):
                entities_list = []
                for e in health_entities["entities"][:15]:
                    entities_list.append(f"- {e['text']} (Category: {e['category']}, Confidence: {e['confidence']:.2f})")
                entities_context = "\n\nExtracted Medical Entities from Text Analytics:\n" + "\n".join(entities_list)
                context += entities_context
            
            diary_context = ""
            if diary_entries and len(diary_entries) > 0:
                relevant_entries = []
                for entry in diary_entries:
                    if entry.get("entry_type") in ["disease", "medication"]:
                        entry_date = entry.get("timestamp", "")
                        entry_text = entry.get("text", "")
                        entry_type = entry.get("entry_type", "")
                        relevant_entries.append(f"- {entry_type.upper()}: {entry_text} (Logged: {entry_date})")
                
                if relevant_entries:
                    diary_context = "\n\n=== PATIENT HEALTH DIARY ENTRIES (MEDICAL HISTORY) ===\n" + "\n".join(relevant_entries) + "\n=== END DIARY ENTRIES ===\n"
                    context += diary_context
                    print(f"Including {len(relevant_entries)} diary entries in SOAP context:")
                    for entry in relevant_entries:
                        print(f"  - {entry}")
            
            system_prompt = """You are a clinical documentation assistant. Your role is to create professional SOAP notes in standard clinical format.

CRITICAL RULES:
1. ONLY use information explicitly mentioned in the input. DO NOT add details that were not provided.
2. Write as a clinical document, not a conversation. Use third person, objective medical language.
3. Do NOT use "you", "you should", "you mentioned", or any direct address to the patient.
4. Use concise, professional clinical phrasing. Avoid long paragraphs.
5. Format your response EXACTLY as follows with clear section headers:

===SUBJECTIVE===
[Content here]

===OBJECTIVE===
[Content here]

===ASSESSMENT===
[Content here]

===PLAN===
[Content here]"""

            diary_instruction = ""
            if diary_context:
                diary_instruction = "\n\nCRITICAL: The patient has logged health diary entries above showing their medical history. You MUST reference these entries in your SOAP note:\n\n1. SUBJECTIVE section: Include ALL diseases/conditions and medications from diary entries in the medical history. For example: 'Past medical history: Diabetes type 3 (per patient diary). Current medications: [list from diary].'\n\n2. ASSESSMENT section: You MUST consider existing conditions from diary when making diagnoses. If patient has diabetes type 3, this significantly affects assessment. State: 'Primary: [diagnosis]. Patient's history of [disease from diary] is relevant as [explanation].'\n\n3. PLAN section: Account for existing medications and conditions. Check for interactions, contraindications, or necessary adjustments based on diary entries.\n\nDO NOT ignore diary entries. They are part of the patient's documented medical history and must be included."
            
            user_prompt = f"""Create a clinical SOAP note from this patient dictation. Write as a professional medical document.

Patient dictation:
{context}
{diary_instruction}

IMPORTANT: The diary entries shown above are PART OF THE PATIENT'S MEDICAL RECORD. You MUST include them in your SOAP note. They are not optional - they are documented medical history.

Generate a SOAP note in clinical format:

===SUBJECTIVE===
Document what the patient reported AND their medical history from diary entries:
- Chief complaint in patient's words
- History of present illness: symptoms, timing, severity, location (from dictation)
- Past medical history: MUST include ALL diseases/conditions from diary entries (e.g., "Past medical history: Diabetes type 3 per patient diary")
- Current medications: MUST include ALL medications from diary entries
- Write in third person, concise clinical language
- Example: "Patient reports [symptom]. Past medical history: [list ALL diseases from diary]. Current medications: [list ALL medications from diary]. Denies [if mentioned]."

===OBJECTIVE===
Document only measurable or observable findings:
- Vital signs if mentioned (BP, HR, RR, Temp, O2 sat)
- Physical examination findings if described
- Test results, lab values, or imaging if mentioned
- If no objective findings were provided, state: "No objective findings documented."
- Use third person, objective clinical language
- Keep it concise and factual

===ASSESSMENT===
Provide differential diagnoses with clinical reasoning:
- Most likely diagnosis based on symptom pattern AND existing conditions from diary
- 2-4 differential diagnoses ranked by likelihood
- Brief clinical reasoning for each
- MANDATORY: You MUST reference diseases/conditions from diary entries in your assessment
- If patient has diabetes type 3 in diary, you MUST state how this affects the current presentation
- Example: "Primary: Hyperglycemia. Patient's documented history of Diabetes type 3 (per diary) is highly relevant as this condition directly relates to blood sugar dysregulation. The headache may be secondary to hyperglycemia given this history."
- Use medical terminology and standard diagnostic criteria
- Format as concise clinical text, not long paragraphs

===PLAN===
Document clear clinical management steps:
- Medications with dosages if appropriate
- Consider existing medications from diary entries - check for interactions or adjustments needed
- Diagnostic tests to order
- Follow-up recommendations
- Patient education points
- Write as medical steps, not advice or conversation
- Use concise clinical phrasing
- Format with each numbered item on a separate line
- Example format:
1. [Medication] [dose] [frequency]
2. Order [test]
3. Follow-up in [timeframe]
4. [Additional step]

Remember: Write as a clinical document. Use third person. Be concise and professional. Reference diary entries for medical history, existing conditions, and medications."""

            print(f"Calling Azure OpenAI with transcription: {transcription[:100]}...")
            print(f"OpenAI client available: {self.azure_clients.openai_client is not None}")
            
            response = self.azure_clients.openai_client.chat.completions.create(
                model=self.azure_clients.openai_deployment,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.4,
                max_tokens=2000
            )
            
            soap_text = response.choices[0].message.content.strip()
            print(f"AI Response received (length: {len(soap_text)}): {soap_text[:200]}...")
            
            soap_note = self._parse_soap_response(soap_text, transcription)
            print(f"Parsed SOAP note - Subjective: {len(soap_note.get('subjective', ''))} chars, Assessment: {len(soap_note.get('assessment', ''))} chars")
            
            if not soap_note.get("assessment") or "pending" in soap_note.get("assessment", "").lower() or "to be" in soap_note.get("assessment", "").lower():
                print("WARNING: AI generated placeholder text, trying again with more explicit instructions")
                return self._retry_soap_generation(transcription, health_entities, diary_entries)
            
            return soap_note
        except Exception as e:
            print(f"Error generating SOAP note: {e}")
            import traceback
            traceback.print_exc()
            return self._generate_fallback_soap(transcription, health_entities)
    
    def update_soap_incremental(self, new_text_chunk: str, current_soap: Dict[str, str], full_transcript: str, diary_entries: Optional[List[Dict]] = None) -> Dict[str, str]:
        if not self.azure_clients.openai_client:
            return current_soap
        
        try:
            diary_context = ""
            if diary_entries and len(diary_entries) > 0:
                relevant_entries = []
                for entry in diary_entries:
                    if entry.get("entry_type") in ["disease", "medication"]:
                        entry_date = entry.get("timestamp", "")
                        entry_text = entry.get("text", "")
                        entry_type = entry.get("entry_type", "")
                        relevant_entries.append(f"- {entry_type.upper()}: {entry_text} (Logged: {entry_date})")
                
                if relevant_entries:
                    diary_context = "\n\n=== PATIENT HEALTH DIARY ENTRIES (MEDICAL HISTORY) ===\n" + "\n".join(relevant_entries) + "\n=== END DIARY ENTRIES ===\n"
            
            has_subjective = bool(current_soap.get('subjective', '').strip())
            has_assessment = bool(current_soap.get('assessment', '').strip())
            has_plan = bool(current_soap.get('plan', '').strip())
            
            priority_instruction = ""
            if not has_subjective:
                priority_instruction = "\n\nPRIORITY: Generate Subjective section FIRST. Extract the chief complaint and initial symptoms from the transcript immediately."
            elif not has_assessment:
                priority_instruction = "\n\nPRIORITY: Generate Assessment section next. Provide an early rough hypothesis based on current symptoms. It can be refined later."
            elif not has_plan:
                priority_instruction = "\n\nPRIORITY: Generate Plan section. Assessment should already exist."
            
            update_prompt = f"""You are updating a clinical SOAP note incrementally during live transcription. You have the current SOAP note state and transcript.

Current SOAP Note State:
Subjective: {current_soap.get('subjective', '')}
Objective: {current_soap.get('objective', 'No objective findings documented.')}
Assessment: {current_soap.get('assessment', '')}
Plan: {current_soap.get('plan', '')}

Full transcript so far: {full_transcript}
New text chunk to incorporate: {new_text_chunk}
{diary_context}
{priority_instruction}

Your task: Update the SOAP note by incorporating the new information. Follow these priorities:
1. SUBJECTIVE must appear FIRST - extract chief complaint and symptoms immediately
2. ASSESSMENT appears next - provide early rough hypothesis that can refine over time
3. PLAN appears later - only after assessment is established
4. OBJECTIVE - document only if mentioned, otherwise keep "No objective findings documented"

Rules:
- If Subjective is empty, generate it NOW from the transcript
- If Assessment is empty but Subjective exists, generate an early hypothesis
- If Plan is empty but Assessment exists, generate a basic plan
- Merge new information into existing sections
- Keep existing content that is still valid
- Maintain clinical format and third-person language
- Reference diary entries if relevant

Return the updated SOAP note in this exact format:

===SUBJECTIVE===
[Updated subjective section]

===OBJECTIVE===
[Updated objective section]

===ASSESSMENT===
[Updated assessment section]

===PLAN===
[Updated plan section]"""

            response = self.azure_clients.openai_client.chat.completions.create(
                model=self.azure_clients.openai_deployment,
                messages=[
                    {"role": "system", "content": "You are a clinical documentation assistant. Update SOAP notes incrementally by merging new information into existing sections."},
                    {"role": "user", "content": update_prompt}
                ],
                temperature=0.3,
                max_tokens=2000
            )
            
            soap_text = response.choices[0].message.content.strip()
            updated_soap = self._parse_soap_response(soap_text, full_transcript)
            
            return updated_soap
        except Exception as e:
            print(f"Error in incremental SOAP update: {e}")
            return current_soap
    
    def _generate_fallback_soap(self, transcription: str, health_entities: Optional[Dict] = None) -> Dict[str, str]:
        print("WARNING: Using rule-based fallback. OpenAI client should be configured for dynamic AI analysis.")
        transcription_lower = transcription.lower()
        
        symptoms_found = []
        if health_entities and health_entities.get("entities"):
            symptoms_found = [e['text'] for e in health_entities["entities"] if e.get('category') in ['Symptom', 'Condition', 'Diagnosis', 'BodyStructure']]
        
        has_fever = "fever" in transcription_lower or "temperature" in transcription_lower or "hot" in transcription_lower
        has_pain = "pain" in transcription_lower or "hurts" in transcription_lower or "ache" in transcription_lower or "sore" in transcription_lower
        has_swelling = "swelling" in transcription_lower or "swollen" in transcription_lower
        has_cough = "cough" in transcription_lower
        has_headache = "headache" in transcription_lower or "head" in transcription_lower and "ache" in transcription_lower
        has_nausea = "nausea" in transcription_lower or "nauseous" in transcription_lower
        has_diarrhea = "diarrhea" in transcription_lower or "diarrhoea" in transcription_lower
        has_rash = "rash" in transcription_lower
        neck_involved = "neck" in transcription_lower
        chest_involved = "chest" in transcription_lower or "breast" in transcription_lower
        abdominal_involved = "stomach" in transcription_lower or "abdomen" in transcription_lower or "belly" in transcription_lower
        facial_involved = "cheek" in transcription_lower or "face" in transcription_lower or "jaw" in transcription_lower
        
        subjective = f"Chief Complaint: {transcription}\nHistory of Present Illness: Patient reports {transcription.lower()}"
        
        objective_parts = []
        if has_fever:
            objective_parts.append("Temperature measurement indicated")
        if has_pain:
            objective_parts.append("Pain assessment and location-specific examination")
        if has_swelling:
            objective_parts.append("Examination of affected area for swelling, erythema, warmth")
        if neck_involved:
            objective_parts.append("Neck examination and lymph node palpation")
        if facial_involved:
            objective_parts.append("Facial and parotid gland examination")
        if chest_involved:
            objective_parts.append("Chest auscultation and respiratory assessment")
        if abdominal_involved:
            objective_parts.append("Abdominal examination and palpation")
        if has_cough:
            objective_parts.append("Respiratory examination and lung auscultation")
        if has_rash:
            objective_parts.append("Skin examination and rash characterization")
        
        objective = "Vital signs assessment. " + ". ".join(objective_parts) + ". General physical examination." if objective_parts else "Complete physical examination and vital signs assessment."
        
        assessment_parts = []
        if has_swelling and facial_involved and has_fever:
            assessment_parts.append("Primary Diagnosis: Mumps, parotitis, or sialadenitis")
            assessment_parts.append("Differential Diagnoses: 1) Lymphadenitis 2) Viral parotitis 3) Bacterial sialadenitis")
            assessment_parts.append("Clinical Reasoning: Bilateral or unilateral facial swelling with fever and neck involvement suggests infectious process affecting salivary glands or lymph nodes")
        elif has_fever and neck_involved and has_pain:
            assessment_parts.append("Primary Diagnosis: Cervical lymphadenitis or upper respiratory infection")
            assessment_parts.append("Differential Diagnoses: 1) Viral infection (EBV, CMV) 2) Bacterial lymphadenitis 3) Inflammatory condition")
            assessment_parts.append("Clinical Reasoning: Fever with neck pain and possible lymph node involvement indicates infectious or inflammatory process")
        elif has_headache and has_nausea:
            assessment_parts.append("Primary Diagnosis: Migraine or tension headache")
            assessment_parts.append("Differential Diagnoses: 1) Tension headache 2) Viral syndrome 3) Intracranial pathology (less likely)")
            assessment_parts.append("Clinical Reasoning: Headache with nausea is classic migraine presentation, though other causes should be considered")
        elif has_cough and has_fever:
            assessment_parts.append("Primary Diagnosis: Upper respiratory infection or pneumonia")
            assessment_parts.append("Differential Diagnoses: 1) Viral URI 2) Bacterial pneumonia 3) Bronchitis")
            assessment_parts.append("Clinical Reasoning: Cough with fever suggests respiratory tract infection")
        elif has_diarrhea and has_fever:
            assessment_parts.append("Primary Diagnosis: Gastroenteritis")
            assessment_parts.append("Differential Diagnoses: 1) Viral gastroenteritis 2) Bacterial infection 3) Food poisoning")
            assessment_parts.append("Clinical Reasoning: Diarrhea with fever indicates gastrointestinal infection")
        elif has_rash and has_fever:
            assessment_parts.append("Primary Diagnosis: Viral exanthem or drug reaction")
            assessment_parts.append("Differential Diagnoses: 1) Viral rash (measles, rubella, etc.) 2) Drug reaction 3) Allergic reaction")
            assessment_parts.append("Clinical Reasoning: Fever with rash suggests viral illness or hypersensitivity reaction")
        else:
            symptom_list = []
            if has_fever: symptom_list.append("fever")
            if has_pain: symptom_list.append("pain")
            if has_swelling: symptom_list.append("swelling")
            if has_cough: symptom_list.append("cough")
            if has_headache: symptom_list.append("headache")
            if has_nausea: symptom_list.append("nausea")
            if symptoms_found:
                symptom_list.extend([s for s in symptoms_found[:3] if s not in symptom_list])
            
            assessment_parts.append(f"Primary Diagnosis: Clinical assessment based on symptom pattern ({', '.join(symptom_list[:4])})")
            assessment_parts.append("Differential Diagnoses: Further evaluation needed to narrow differential")
            assessment_parts.append("Clinical Reasoning: Symptom constellation requires comprehensive evaluation")
        
        assessment = ". ".join(assessment_parts)
        
        plan_items = []
        if has_fever:
            plan_items.append("Antipyretic: Acetaminophen 500-1000mg q6h or Ibuprofen 400-600mg q6h for fever")
        if has_pain:
            plan_items.append("Analgesia as needed for pain management")
        if has_swelling and facial_involved:
            plan_items.append("Warm compresses to affected area")
            plan_items.append("Consider viral serology (mumps, EBV) and CBC with differential")
        elif has_fever and neck_involved:
            plan_items.append("CBC, inflammatory markers (ESR, CRP), and consider imaging if abscess suspected")
        elif has_headache:
            plan_items.append("Headache management with appropriate analgesics")
            plan_items.append("Consider neuroimaging if red flag symptoms present")
        elif has_cough:
            plan_items.append("Chest X-ray if pneumonia suspected, symptomatic treatment")
        elif has_diarrhea:
            plan_items.append("Stool studies if indicated, hydration, anti-diarrheal if appropriate")
        else:
            plan_items.append("Symptomatic treatment based on specific symptoms")
            plan_items.append("Diagnostic workup as clinically indicated")
        
        plan_items.append("Follow-up in 3-5 days or sooner if symptoms worsen")
        plan_items.append("Patient education on symptom management and when to seek immediate care")
        
        plan = "1. " + " 2. ".join(plan_items)
        
        return {
            "subjective": subjective,
            "objective": objective,
            "assessment": assessment,
            "plan": plan
        }
    
    def _retry_soap_generation(self, transcription: str, health_entities: Optional[Dict] = None, diary_entries: Optional[List[Dict]] = None) -> Dict[str, str]:
        try:
            context = transcription
            if health_entities and health_entities.get("entities"):
                entities_text = ", ".join([e['text'] for e in health_entities["entities"][:10]])
                context += f"\n\nMedical entities found: {entities_text}"
            
            if diary_entries and len(diary_entries) > 0:
                relevant_entries = []
                for entry in diary_entries:
                    if entry.get("entry_type") in ["disease", "medication"]:
                        entry_date = entry.get("timestamp", "")
                        entry_text = entry.get("text", "")
                        entry_type = entry.get("entry_type", "")
                        relevant_entries.append(f"- {entry_type.upper()}: {entry_text} (Logged: {entry_date})")
                
                if relevant_entries:
                    context += "\n\nPatient Health Diary Entries (RELEVANT MEDICAL HISTORY):\n" + "\n".join(relevant_entries)
            
            retry_prompt = f"""Create a clinical SOAP note from this patient dictation. Write as a professional medical document in third person. Do not use "you" or conversational language. Reference any diseases/medications from diary entries in your assessment and plan.

Patient dictation: {context}

Format your response EXACTLY as:

===SUBJECTIVE===
[Only what patient reported - third person, clinical language]

===OBJECTIVE===
[Only measurable/observable findings, or "No objective findings documented" if none]

===ASSESSMENT===
[Differential diagnoses with reasoning - concise clinical text]

===PLAN===
[Clinical management steps - medical phrasing, not advice. Format with each numbered item on a separate line:
1. First step
2. Second step
3. Third step]

Write as a clinical document. Use third person. Be concise. Only use information actually mentioned."""

            response = self.azure_clients.openai_client.chat.completions.create(
                model=self.azure_clients.openai_deployment,
                messages=[
                    {"role": "system", "content": "You are a medical assistant. Generate complete SOAP notes with real diagnoses and treatment plans. Never use placeholder text."},
                    {"role": "user", "content": retry_prompt}
                ],
                temperature=0.5,
                max_tokens=2000
            )
            
            soap_text = response.choices[0].message.content.strip()
            return self._parse_soap_response(soap_text, transcription)
        except:
            return self._generate_fallback_soap(transcription, health_entities)
    
    def _parse_soap_response(self, soap_text: str, transcription: str = "") -> Dict[str, str]:
        sections = {
            "subjective": "",
            "objective": "",
            "assessment": "",
            "plan": ""
        }
        
        text_lower = soap_text.lower()
        
        section_markers = {
            "subjective": ["===subjective===", "subjective:", "**subjective**", "subjective (s):", "s:"],
            "objective": ["===objective===", "objective:", "**objective**", "objective (o):", "o:"],
            "assessment": ["===assessment===", "assessment:", "**assessment**", "assessment (a):", "a:", "impression:", "diagnosis:"],
            "plan": ["===plan===", "plan:", "**plan**", "plan (p):", "p:", "treatment plan:"]
        }
        
        section_keywords = {
            "subjective": ["subjective", "chief complaint", "history of present illness", "hpi"],
            "objective": ["objective", "physical examination", "vital signs", "exam", "objective findings"],
            "assessment": ["assessment", "impression", "diagnosis", "clinical assessment", "differential diagnosis", "primary diagnosis"],
            "plan": ["plan", "treatment", "follow-up", "management", "treatment plan"]
        }
        
        lines = soap_text.split("\n")
        current_section = None
        collecting = False
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                if collecting and current_section:
                    sections[current_section] += "\n"
                continue
                
            line_lower = line_stripped.lower()
            
            section_found = False
            for section, markers in section_markers.items():
                for marker in markers:
                    if line_lower.startswith(marker):
                        current_section = section
                        collecting = True
                        section_found = True
                        remaining = line_stripped[len(marker):].strip().lstrip(":").strip().lstrip("-").strip()
                        if remaining:
                            sections[current_section] = remaining
                        else:
                            sections[current_section] = ""
                        break
                if section_found:
                    break
            
            if not section_found and collecting and current_section:
                next_section_marker = False
                for other_section, other_markers in section_markers.items():
                    if other_section != current_section:
                        for marker in other_markers:
                            if line_lower.startswith(marker):
                                next_section_marker = True
                                break
                        if next_section_marker:
                            break
                
                if not next_section_marker:
                    if sections[current_section] and not sections[current_section].endswith("\n"):
                        sections[current_section] += "\n"
                    sections[current_section] += line_stripped
        
        if not any(sections.values()):
            for section, keywords in section_keywords.items():
                for kw in keywords:
                    if kw in text_lower:
                        idx = text_lower.find(kw)
                        if idx != -1:
                            start_idx = idx + len(kw)
                            next_section_idx = len(soap_text)
                            for other_section, other_keywords in section_keywords.items():
                                if other_section != section:
                                    for other_kw in other_keywords:
                                        other_idx = text_lower.find(other_kw, start_idx)
                                        if other_idx != -1 and other_idx < next_section_idx:
                                            next_section_idx = other_idx
                            sections[section] = soap_text[start_idx:next_section_idx].strip().lstrip(":").strip()
                            break
                    if sections[section]:
                        break
        
        if not any(sections.values()):
            paragraphs = [p.strip() for p in soap_text.split("\n\n") if p.strip()]
            if len(paragraphs) >= 4:
                sections["subjective"] = paragraphs[0]
                sections["objective"] = paragraphs[1]
                sections["assessment"] = paragraphs[2]
                sections["plan"] = paragraphs[3]
            elif len(paragraphs) > 0:
                sections["subjective"] = paragraphs[0]
                if len(paragraphs) > 1:
                    sections["objective"] = paragraphs[1]
                if len(paragraphs) > 2:
                    sections["assessment"] = paragraphs[2]
                if len(paragraphs) > 3:
                    sections["plan"] = paragraphs[3]
            else:
                sections["subjective"] = soap_text
        
        for section in sections:
            sections[section] = sections[section].strip()
            if not sections[section]:
                if section == "subjective" and transcription:
                    sections[section] = transcription
                else:
                    sections[section] = f"{section.capitalize()} information to be documented."
        
        if not sections["subjective"] or sections["subjective"] == "Subjective information to be documented.":
            sections["subjective"] = transcription if transcription else "Patient symptoms and complaints to be documented."
        
        return sections
