from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import httpx
import asyncio
from .azure_clients import AzureClients


class DiaryPipeline:
    
    def __init__(self, azure_clients: AzureClients):
        self.azure_clients = azure_clients
    
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
        
        time_series = []
        for i, entry in enumerate(entries):
            time_series.append({
                "date": entry.get("timestamp", datetime.now()).isoformat(),
                "type": entry.get("entry_type", "food")
            })
        
        return {
            "total_entries": len(entries),
            "date_range": {
                "start": min(dates).isoformat() if dates else datetime.now().isoformat(),
                "end": max(dates).isoformat() if dates else datetime.now().isoformat()
            },
            "sentiment_trend": [],
            "common_diseases": [
                {"disease": k, "count": v} for k, v in sorted(diseases.items(), key=lambda x: x[1], reverse=True)[:5]
            ],
            "mood_patterns": [
                {"mood": k, "count": v} for k, v in moods.items()
            ],
            "suggestions": suggestions,
            "visualization_data": {
                "time_series": time_series,
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
        self.nlm_api_base = "https://clinicaltables.nlm.nih.gov/api/conditions/v3/search"
    
    async def _query_nlm_conditions(self, symptoms: List[str], max_results: int = 50) -> List[Dict[str, Any]]:
        try:
            symptom_query = " ".join(symptoms[:5])
            params = {
                "terms": symptom_query,
                "maxList": min(max_results, 50),
                "df": "primary_name,consumer_name",
                "ef": "icd10cm_codes,icd10cm,term_icd9_code,term_icd9_text"
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.nlm_api_base, params=params)
                response.raise_for_status()
                data = response.json()
            
            if len(data) < 2:
                return []
            
            total_count = data[0]
            codes = data[1] if len(data) > 1 else []
            extra_data = data[2] if len(data) > 2 else {}
            display_data = data[3] if len(data) > 3 else []
            
            conditions = []
            icd10_codes_array = extra_data.get("icd10cm_codes", []) if extra_data else []
            icd10_list_array = extra_data.get("icd10cm", []) if extra_data else []
            icd9_code_array = extra_data.get("term_icd9_code", []) if extra_data else []
            icd9_text_array = extra_data.get("term_icd9_text", []) if extra_data else []
            
            for i, code in enumerate(codes):
                condition_name = display_data[i][0] if i < len(display_data) and len(display_data[i]) > 0 else ""
                consumer_name = display_data[i][1] if i < len(display_data) and len(display_data[i]) > 1 else condition_name
                
                icd10_codes = icd10_codes_array[i] if i < len(icd10_codes_array) else []
                icd10_list = icd10_list_array[i] if i < len(icd10_list_array) else []
                icd9_code = icd9_code_array[i] if i < len(icd9_code_array) else None
                icd9_text = icd9_text_array[i] if i < len(icd9_text_array) else None
                
                if isinstance(icd10_codes, str):
                    icd10_codes = [icd10_codes] if icd10_codes else []
                elif not isinstance(icd10_codes, list):
                    icd10_codes = []
                
                conditions.append({
                    "code": code,
                    "primary_name": condition_name,
                    "consumer_name": consumer_name or condition_name,
                    "icd10_codes": icd10_codes,
                    "icd10_list": icd10_list if isinstance(icd10_list, list) else [],
                    "icd9_code": icd9_code,
                    "icd9_text": icd9_text
                })
            
            print(f"[DIFFERENTIAL] Found {len(conditions)} possible conditions from NLM API")
            return conditions[:max_results]
        except Exception as e:
            print(f"[DIFFERENTIAL] Error querying NLM API: {e}")
            return []
    
    async def _perform_differential_diagnosis(self, transcription: str, diary_entries: Optional[List[Dict]] = None, gender: Optional[str] = None) -> Dict[str, Any]:
        if not self.azure_clients.openai_client:
            return {"possible_conditions": [], "eliminated_conditions": [], "final_diagnoses": []}
        
        try:
            symptom_extraction_prompt = f"""Extract all symptoms, signs, and clinical findings from this patient dictation. List them as a simple comma-separated list of symptoms.

Patient dictation:
{transcription}

Respond with ONLY a comma-separated list of symptoms, nothing else. Example: "headache, nausea, fever, facial swelling"
"""
            
            response = self.azure_clients.openai_client.chat.completions.create(
                model=self.azure_clients.openai_deployment,
                messages=[
                    {"role": "system", "content": "You are a medical symptom extractor. Extract symptoms from patient descriptions."},
                    {"role": "user", "content": symptom_extraction_prompt}
                ],
                temperature=0.2,
                max_tokens=200
            )
            
            symptoms_text = response.choices[0].message.content.strip()
            symptoms = [s.strip() for s in symptoms_text.split(",") if s.strip()]
            print(f"[DIFFERENTIAL] Extracted symptoms: {symptoms}")
            
            if not symptoms:
                return {"possible_conditions": [], "eliminated_conditions": [], "final_diagnoses": []}
            
            conditions = await self._query_nlm_conditions(symptoms, max_results=30)
            
            if not conditions:
                print("[DIFFERENTIAL] No conditions found from NLM API")
                return {"possible_conditions": [], "eliminated_conditions": [], "final_diagnoses": []}
            
            diary_context = ""
            if diary_entries:
                allergies = []
                genetic_conditions = []
                chronic_conditions = []
                past_illnesses = []
                medications = []
                vitals = []
                lifestyle_risks = []
                family_history = []
                
                for entry in diary_entries:
                    entry_type = entry.get("entry_type", "").lower()
                    entry_text = entry.get("text", "").strip()
                    
                    if not entry_text:
                        continue
                    
                    if entry_type == "chronic_condition":
                        chronic_conditions.append(entry_text)
                    elif entry_type == "genetic_condition":
                        genetic_conditions.append(entry_text)
                    elif entry_type == "allergy":
                        allergies.append(entry_text)
                    elif entry_type == "past_illness":
                        past_illnesses.append(entry_text)
                    elif entry_type == "medication":
                        medications.append(entry_text)
                    elif entry_type == "vitals":
                        vitals.append(entry_text)
                    elif entry_type == "lifestyle_risk":
                        lifestyle_risks.append(entry_text)
                    elif entry_type == "family_history":
                        family_history.append(entry_text)
                
                diary_parts = []
                if chronic_conditions:
                    diary_parts.append(f"CHRONIC CONDITIONS (from patient diary): {', '.join(chronic_conditions)}")
                if genetic_conditions:
                    diary_parts.append(f"GENETIC CONDITIONS (from patient diary): {', '.join(genetic_conditions)}")
                if allergies:
                    diary_parts.append(f"ALLERGIES (from patient diary): {', '.join(allergies)}")
                if past_illnesses:
                    diary_parts.append(f"PAST MEDICAL HISTORY (from patient diary): {', '.join(past_illnesses)}")
                if medications:
                    diary_parts.append(f"CURRENT/PAST MEDICATIONS (from patient diary): {', '.join(medications)}")
                if vitals:
                    diary_parts.append(f"VITALS (from patient diary): {', '.join(vitals)}")
                if lifestyle_risks:
                    diary_parts.append(f"LIFESTYLE RISK FACTORS (from patient diary): {', '.join(lifestyle_risks)}")
                if family_history:
                    diary_parts.append(f"FAMILY HISTORY (from patient diary): {', '.join(family_history)}")
                
                if diary_parts:
                    diary_context = "\n".join(diary_parts)
                    print(f"[DIFFERENTIAL] Diary context prepared: {len(chronic_conditions)} chronic conditions, {len(genetic_conditions)} genetic conditions, {len(allergies)} allergies, {len(past_illnesses)} past illnesses, {len(medications)} medications, {len(vitals)} vitals, {len(lifestyle_risks)} lifestyle risks, {len(family_history)} family history entries")
            
            conditions_list = "\n".join([
                f"{i+1}. {c['consumer_name']} (ICD-10: {', '.join(c['icd10_codes']) if c['icd10_codes'] else 'N/A'})"
                for i, c in enumerate(conditions[:25])
            ])
            
            elimination_prompt = f"""You are Dr. House performing differential diagnosis. Your job is to ELIMINATE impossible diagnoses based on contradictions.

PATIENT GENDER: {gender.upper() if gender else "Not specified"}

PATIENT SYMPTOMS (from current visit):
{', '.join(symptoms)}

PATIENT MEDICAL HISTORY (from health diary):
{diary_context if diary_context else "No significant medical history documented in diary"}

CRITICAL: Pay special attention to these factors for elimination:
- FAMILY HISTORY: MANDATORY - Family history is a critical risk factor. If a condition appears in family history (e.g., "Mother → breast cancer at 42", "Father → colon cancer", "Sister → type 1 diabetes"), this significantly increases the patient's risk for that condition. DO NOT eliminate conditions that match family history - instead, prioritize them. However, if family history shows a condition that contradicts a possible diagnosis, consider eliminating. Example: If family history shows "Father → hemophilia" and patient is male, this is highly relevant for bleeding disorders.
- CHRONIC CONDITIONS: These are ongoing conditions the patient has. If a possible diagnosis contradicts or conflicts with a chronic condition, ELIMINATE it. Example: If patient has "asthma" as chronic condition, eliminate diagnoses requiring normal lung function.
- GENETIC CONDITIONS: These are permanent hereditary conditions. If a possible diagnosis contradicts a genetic condition, ELIMINATE it.
- ALLERGIES: If a possible diagnosis would require exposure to an allergen the patient is allergic to, and patient shows no allergic reaction, consider eliminating. If patient has allergy to medication X, eliminate conditions that would require medication X.
- PAST MEDICAL HISTORY: If patient has a past condition that makes a new diagnosis unlikely or impossible, ELIMINATE it.
- MEDICATIONS: If patient is on medication Y that would prevent or contradict condition X, ELIMINATE it. Also check for drug-disease interactions.
- VITALS: Use vital signs to eliminate conditions. Example: If patient has normal blood pressure, eliminate hypertensive crisis. If patient has elevated temperature, consider infectious causes.
- LIFESTYLE RISK FACTORS: Consider lifestyle factors when eliminating. Example: If patient is non-smoker, eliminate smoking-related conditions. If patient has sedentary lifestyle, consider cardiovascular risks.

POSSIBLE CONDITIONS (from medical database - NLM Clinical Tables):
{conditions_list}

TASK: Analyze each condition and ELIMINATE those that are IMPOSSIBLE based on:
1. GENDER contradictions: If a condition is gender-specific and patient's gender doesn't match, ELIMINATE it. Examples: Breast cancer in males (unless rare cases), prostate cancer in females, ovarian cancer in males, testicular cancer in females. If patient is MALE, eliminate female-specific conditions. If patient is FEMALE, eliminate male-specific conditions.
2. FAMILY HISTORY risk assessment: MANDATORY - Family history is a critical factor. If family history shows a condition (e.g., "Mother → breast cancer", "Father → colon cancer", "Sister → type 1 diabetes"), this INCREASES risk for that condition, so DO NOT eliminate it. However, if family history contradicts a possible diagnosis, consider eliminating. Example: If family history shows "Father → hemophilia" and patient is male, prioritize bleeding disorders. If family history shows "Mother → breast cancer at 42" and patient is female, breast cancer should be considered, not eliminated.
3. Symptom contradictions: If a condition requires symptom X but patient has symptom Y that contradicts it, ELIMINATE it
4. CHRONIC CONDITION contradictions: If patient has CHRONIC CONDITION Z that makes condition X impossible or contradictory, ELIMINATE it. Example: If patient has "diabetes" as chronic condition and a possible condition requires normal glucose metabolism, ELIMINATE it.
5. GENETIC CONDITION contradictions: If patient has genetic condition G that contradicts condition X, ELIMINATE it
6. ALLERGY contradictions: If condition X would require exposure to allergen patient is allergic to, and no allergic reaction is present, ELIMINATE it. If condition requires medication patient is allergic to, ELIMINATE it.
7. Past medical history contradictions: If patient has past condition Z that makes condition X impossible, ELIMINATE it
8. Medication interactions: If patient is on medication Y that would prevent or contradict condition X, ELIMINATE it. Check for drug-disease interactions.
9. VITALS contradictions: If patient's vital signs contradict what condition X requires, ELIMINATE it. Example: Normal BP eliminates hypertensive crisis.
10. LIFESTYLE RISK contradictions: If condition X requires lifestyle factor patient doesn't have, consider eliminating. Example: Non-smoker eliminates smoking-related conditions.

For each condition, determine:
- KEEP: Condition is still possible given symptoms, active diseases, and history
- ELIMINATE: Condition is impossible due to contradictions with active diseases, symptoms, or history

Respond in this EXACT format:
KEEP: [condition number] - [condition name] - [brief reason why it's still possible, referencing active diseases if relevant]
ELIMINATE: [condition number] - [condition name] - [brief reason why it's impossible, specifically mentioning which active disease/past condition/medication contradicts it]

List ALL conditions. Be thorough and logical. Think like Dr. House - eliminate what doesn't fit. Always reference the specific disease/condition from the diary when eliminating."""
            
            response = self.azure_clients.openai_client.chat.completions.create(
                model=self.azure_clients.openai_deployment,
                messages=[
                    {"role": "system", "content": "You are a diagnostic expert like Dr. House. You eliminate impossible diagnoses through logical deduction based on symptom patterns and medical history."},
                    {"role": "user", "content": elimination_prompt}
                ],
                temperature=0.3,
                max_tokens=2000
            )
            
            elimination_text = response.choices[0].message.content.strip()
            print(f"[DIFFERENTIAL] Elimination analysis:\n{elimination_text[:500]}...")
            
            kept_conditions = []
            eliminated_conditions = []
            
            for line in elimination_text.split("\n"):
                line = line.strip()
                if line.startswith("KEEP:"):
                    parts = line.replace("KEEP:", "").strip().split(" - ", 2)
                    if len(parts) >= 2:
                        try:
                            cond_num = int(parts[0].strip()) - 1
                            if 0 <= cond_num < len(conditions):
                                kept_conditions.append({
                                    "condition": conditions[cond_num],
                                    "reason": parts[2] if len(parts) > 2 else "Possible based on symptoms"
                                })
                        except:
                            pass
                elif line.startswith("ELIMINATE:"):
                    parts = line.replace("ELIMINATE:", "").strip().split(" - ", 2)
                    if len(parts) >= 2:
                        try:
                            cond_num = int(parts[0].strip()) - 1
                            if 0 <= cond_num < len(conditions):
                                eliminated_conditions.append({
                                    "condition": conditions[cond_num],
                                    "reason": parts[2] if len(parts) > 2 else "Contradicts symptoms or history"
                                })
                        except:
                            pass
            
            print(f"[DIFFERENTIAL] Kept {len(kept_conditions)} conditions, eliminated {len(eliminated_conditions)}")
            
            return {
                "possible_conditions": conditions,
                "kept_conditions": kept_conditions,
                "eliminated_conditions": eliminated_conditions,
                "symptoms": symptoms,
                "diary_context": diary_context
            }
        except Exception as e:
            print(f"[DIFFERENTIAL] Error in differential diagnosis: {e}")
            import traceback
            traceback.print_exc()
            return {"possible_conditions": [], "eliminated_conditions": [], "final_diagnoses": []}
    
    async def generate_soap_note(self, transcription: str, health_entities: Optional[Dict] = None, diary_entries: Optional[List[Dict]] = None, gender: Optional[str] = None) -> Dict[str, str]:
        if not self.azure_clients.openai_client:
            print("WARNING: OpenAI client not available, using fallback SOAP generation")
            return self._generate_fallback_soap(transcription, health_entities)
        
        try:
            differential_result = await self._perform_differential_diagnosis(transcription, diary_entries, gender)
            kept_diagnoses = [dc["condition"]["consumer_name"] for dc in differential_result.get("kept_conditions", [])]
            eliminated_diagnoses = [dc["condition"]["consumer_name"] for dc in differential_result.get("eliminated_conditions", [])]
            
            differential_context = ""
            if kept_diagnoses:
                differential_context = f"\n\n=== DIFFERENTIAL DIAGNOSIS ANALYSIS ===\n"
                differential_context += f"Possible diagnoses (after elimination): {', '.join(kept_diagnoses[:5])}\n"
                if eliminated_diagnoses:
                    differential_context += f"Eliminated diagnoses (contradictions found): {', '.join(eliminated_diagnoses[:5])}\n"
                differential_context += "=== END DIFFERENTIAL ANALYSIS ===\n"
            
            context = transcription + differential_context
            entities_context = ""
            if health_entities and health_entities.get("entities"):
                entities_list = []
                for e in health_entities["entities"][:15]:
                    entities_list.append(f"- {e['text']} (Category: {e['category']}, Confidence: {e['confidence']:.2f})")
                entities_context = "\n\nExtracted Medical Entities from Text Analytics:\n" + "\n".join(entities_list)
                context += entities_context
            
            diary_context = ""
            if diary_entries and len(diary_entries) > 0:
                medical_entries = []
                medication_entries = []
                
                for entry in diary_entries:
                    entry_type = entry.get("entry_type", "").lower()
                    entry_text = entry.get("text", "").strip()
                    entry_date = entry.get("timestamp", "")
                    
                    if not entry_text:
                        continue
                    
                    if entry_type == "chronic_condition":
                        medical_entries.append(f"CHRONIC CONDITION: {entry_text} (Logged: {entry_date})")
                    elif entry_type == "genetic_condition":
                        medical_entries.append(f"GENETIC CONDITION: {entry_text} (Logged: {entry_date})")
                    elif entry_type == "allergy":
                        medical_entries.append(f"ALLERGY: {entry_text} (Logged: {entry_date})")
                    elif entry_type == "past_illness":
                        medical_entries.append(f"PAST ILLNESS: {entry_text} (Logged: {entry_date})")
                    elif entry_type == "vitals":
                        medical_entries.append(f"VITALS: {entry_text} (Logged: {entry_date})")
                    elif entry_type == "lifestyle_risk":
                        medical_entries.append(f"LIFESTYLE RISK: {entry_text} (Logged: {entry_date})")
                    elif entry_type == "family_history":
                        medical_entries.append(f"FAMILY HISTORY: {entry_text} (Logged: {entry_date})")
                    elif entry_type == "medication":
                        medication_entries.append(f"MEDICATION: {entry_text} (Logged: {entry_date})")
                
                if medical_entries or medication_entries:
                    diary_context = "\n\n=== PATIENT HEALTH DIARY ENTRIES (MEDICAL HISTORY) ===\n"
                    if medical_entries:
                        diary_context += "MEDICAL CONDITIONS/FACTORS:\n" + "\n".join(medical_entries) + "\n"
                    if medication_entries:
                        diary_context += "MEDICATIONS:\n" + "\n".join(medication_entries) + "\n"
                    diary_context += "=== END DIARY ENTRIES ===\n"
                    context += diary_context
                    print(f"Including {len(medical_entries)} medical entries and {len(medication_entries)} medication entries in SOAP context:")
                    for entry in medical_entries + medication_entries:
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
                diary_instruction = "\n\nCRITICAL: The patient has logged health diary entries above showing their medical history. You MUST reference these entries in your SOAP note:\n\n1. SUBJECTIVE section: Include ALL medical information from diary entries:\n   - Chronic conditions (e.g., 'Chronic conditions: Asthma, Diabetes (per patient diary)')\n   - Genetic conditions (e.g., 'Genetic conditions: Hemophilia (per patient diary)')\n   - Allergies (e.g., 'Allergies: Penicillin, Peanuts (per patient diary)')\n   - Past medical history (e.g., 'Past medical history: Pneumonia (per patient diary)')\n   - Family history (e.g., 'Family history: Mother → breast cancer at 42, Father → colon cancer (per patient diary)')\n   - Vitals (e.g., 'Vitals: BP 120/80, HR 72 (per patient diary)')\n   - Lifestyle risk factors (e.g., 'Lifestyle: Non-smoker, Sedentary (per patient diary)')\n   - Current medications: [list ALL medications from diary]\n\n2. ASSESSMENT section: You MUST consider ALL diary entries when making diagnoses. MANDATORY: Family history is a critical risk factor. If family history shows a condition (e.g., 'Mother → breast cancer at 42'), this significantly increases the patient's risk for that condition. Reference how chronic conditions, genetic conditions, allergies, family history, vitals, and lifestyle factors affect the diagnosis. State: 'Primary: [diagnosis]. Patient's documented [chronic condition/genetic condition/allergy/family history] from diary is relevant as [explanation].'\n\n3. PLAN section: Account for ALL diary entries. Check for:\n   - Drug-disease interactions (e.g., if patient has asthma, avoid medications that worsen it)\n   - Drug-allergy interactions (e.g., if patient is allergic to penicillin, avoid it)\n   - Disease-disease interactions (e.g., if patient has diabetes, consider how it affects treatment)\n   - Family history-based screening recommendations (e.g., if family history shows breast cancer, recommend appropriate screening)\n   - Vitals-based considerations (e.g., if patient has hypertension, monitor BP)\n   - Lifestyle-based recommendations\n   - Contraindications based on ALL diary entries\n\nDO NOT ignore diary entries. They are part of the patient's documented medical history and must be included. When a condition is listed in the diary, treat it as a confirmed medical fact. Family history entries MUST be considered as significant risk factors."
            
            gender_info = f"\nPATIENT GENDER: {gender.upper() if gender else 'Not specified'}\n" if gender else ""
            
            user_prompt = f"""Create a clinical SOAP note from this patient dictation. Write as a professional medical document.

Patient dictation:
{context}
{diary_instruction}
{gender_info}
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
- CRITICAL: Use the differential diagnosis analysis provided above. The system has already eliminated impossible diagnoses based on symptom contradictions and medical history.
- Primary diagnosis: Choose from the "Possible diagnoses (after elimination)" list above, prioritizing the most likely based on symptom pattern
- 2-4 differential diagnoses: Use the kept diagnoses from the elimination analysis, ranked by likelihood
- For each diagnosis, explain WHY it was kept (not eliminated) and how it fits the symptoms
- MANDATORY: Reference eliminated diagnoses and explain WHY they were ruled out (e.g., "Ruled out [condition] due to [contradiction]")
- MANDATORY: You MUST reference diseases/conditions from diary entries in your assessment
- Example: "Primary: [diagnosis from kept list]. Patient's documented history of [disease from diary] supports this diagnosis. Ruled out [eliminated condition] because [reason from elimination analysis]."
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

Remember: Write as a clinical document. Use third person. Be concise and professional. Reference diary entries for medical history, existing conditions, and medications. Consider patient gender when documenting conditions and treatment plans."""

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
    
    async def update_soap_incremental(self, new_text_chunk: str, current_soap: Dict[str, str], full_transcript: str, diary_entries: Optional[List[Dict]] = None, gender: Optional[str] = None) -> Dict[str, str]:
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
            
            gender_info = f"\nPATIENT GENDER: {gender.upper() if gender else 'Not specified'}\n" if gender else ""
            
            update_prompt = f"""You are updating a clinical SOAP note incrementally during live transcription. You have the current SOAP note state and transcript.

Current SOAP Note State:
Subjective: {current_soap.get('subjective', '')}
Objective: {current_soap.get('objective', 'No objective findings documented.')}
Assessment: {current_soap.get('assessment', '')}
Plan: {current_soap.get('plan', '')}

Full transcript so far: {full_transcript}
New text chunk to incorporate: {new_text_chunk}
{diary_context}
{gender_info}
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
