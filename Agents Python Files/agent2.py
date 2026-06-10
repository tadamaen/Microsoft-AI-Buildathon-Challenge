"""
Agent 2: Triage Decision Classifier

Description:
This agent operates as the clinical router. It ingests the structured JSON output from Agent 1 and determines the overarching category of the patient's distress. By evaluating the presence of physical flags, mental flags, or comorbidities, it decides which specific Retrieval-Augmented Generation (RAG) database lane the query should be routed to (e.g., Physical RAG, Mental RAG, or Intersection RAG).
"""

from pydantic import BaseModel, Field
from typing import Literal

class TriageClassification(BaseModel):
    routing_decision: Literal["ROUTE_TO_PHYSICAL_RAG", "ROUTE_TO_MENTAL_RAG", "ROUTE_TO_INTERSECTION_RAG", "ROUTE_TO_INTAKE_LOOP"] = Field(...)
    physical_flags_present: bool = Field(...)
    mental_flags_present: bool = Field(...)
    comorbidity_detected: bool = Field(...)
    is_data_sufficient: bool = Field(...)
    clinical_reasoning: str = Field(...)

def execute_agent_2(client, agent_1_json_payload: str):
    system_prompt = "You are Agent 2 (Triage Decision Classifier). Take the structured clinical intake data and select an internal routing lane target for documentation lookups."
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": agent_1_json_payload}
    ]
    return client.beta.chat.completions.parse(model="gpt-4o-mini", messages=messages, response_format=TriageClassification).choices[0].message.parsed