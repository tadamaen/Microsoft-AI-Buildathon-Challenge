"""
Agent 12: Check-In Sentiment Analyzer

Description:
This agent operates the natural language processing (NLP) engine for the Weekly Check-In loop. Instead of asking the user to manually rate their pain on a slider, this agent reads the user's free-text reflection of their week. It analyzes the linguistic sentiment and extracts an estimated numeric severity scale (0-10). This integer controls the entire lifecycle of the app, deciding if the user should proceed to the next week or conclude the protocol.
"""

from pydantic import BaseModel, Field

class CheckInAnalysisSchema(BaseModel):
    estimated_severity: int = Field(..., description="Estimate the user's current severity level from 0 to 10 based purely on their textual update.")
    analysis_rationale: str = Field(...)

def execute_agent_12(client, user_reflection_text: str):
    system_prompt = "You are Agent 12, a clinical sentiment analyzer. Read the user's weekly check-in text carefully and estimate their current distress or symptom severity on a strict scale of 0 to 10 (where 10 is unbearable)."
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_reflection_text}
    ]
    return client.beta.chat.completions.parse(model="gpt-4o-mini", messages=messages, response_format=CheckInAnalysisSchema).choices[0].message.parsed