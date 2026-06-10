"""
Agent 4: Clinical Triage Diagnostic Synthesizer

Description:
This agent acts as the medical evaluator. It takes the raw patient symptoms (from Agent 1) and cross-references them against the strict medical guidelines (retrieved by Agent 3). It synthesizes this data to generate a list of potential conditions, explains the underlying mechanical etiologies of why the patient is experiencing these symptoms, and recommends clinical next steps.
"""

from pydantic import BaseModel, Field
from typing import List

class TriageSynthesisSchema(BaseModel): 
    potential_conditions: List[str] = Field(...)
    underlying_mechanisms: str = Field(...)
    recommended_next_steps: List[str] = Field(...)

def execute_agent_4(client, agent_1_json_payload: str, agent_3_literature: str):
    system_prompt = "You are Agent 4 (Triage Diagnostic Synthesizer). Cross-reference raw symptoms with standard knowledge guidelines to generate expected diagnostic considerations and mechanical etiologies."
    user_payload = f"SYMPTOMS:\n{agent_1_json_payload}\n\nGUIDELINES:\n{agent_3_literature}"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_payload}
    ]
    return client.beta.chat.completions.parse(model="gpt-4o-mini", messages=messages, response_format=TriageSynthesisSchema).choices[0].message.parsed