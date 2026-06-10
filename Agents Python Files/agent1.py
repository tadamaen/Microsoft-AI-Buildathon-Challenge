"""
Agent 1: Clinical Intake Parser

Description:
This agent acts as the foundational data extraction node. It ingests raw, unstructured patient payloads (which can include natural language text and OCR data from uploaded medical documents) and parses them into a strict JSON schema. It extracts primary concerns, tracks symptom duration, assigns a quantifiable severity scale, and categorizes symptoms into physical and emotional indicators. It also serves as a gatekeeper, setting a boolean flag (`is_information_complete`) to halt the pipeline if the user's input is too vague.
"""

from pydantic import BaseModel, Field
from typing import List, Optional

class ClinicalIntakeSchema(BaseModel):
    primary_concerns: List[str] = Field(...)
    symptom_duration: Optional[str] = Field(None)
    severity_scale: Optional[int] = Field(None)
    physical_indicators: List[str] = Field(default=[])
    emotional_indicators: List[str] = Field(default=[])
    contextual_triggers: List[str] = Field(default=[])
    is_information_complete: bool = Field(...)
    missing_fields_rationale: Optional[str] = Field(None)

def execute_agent_1(client, user_input_text: str, base64_image: Optional[str] = None, image_type: Optional[str] = None):
    system_prompt = "You are Agent 1 (Clinical Intake Parser). Read the user query and cleanly decompose all explicitly listed or implied physiological, environmental, and mental conditions."
    
    if base64_image:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [
                {"type": "text", "text": f"User Input: {user_input_text}\n\nAnalyze the attached medical document image as well."},
                {"type": "image_url", "image_url": {"url": f"data:{image_type};base64,{base64_image}"}}
            ]}
        ]
        return client.beta.chat.completions.parse(model="gpt-4o-mini", messages=messages, response_format=ClinicalIntakeSchema).choices[0].message.parsed
    else:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input_text}
        ]
        return client.beta.chat.completions.parse(model="gpt-4o-mini", messages=messages, response_format=ClinicalIntakeSchema).choices[0].message.parsed