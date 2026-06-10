"""
Agent 10: Medical Record Scribe & Email Crafter

Description:
This agent is the automated medical scribe. At the conclusion of the patient's lifecycle, it ingests all historical data—initial symptoms, diagnoses, and every single tracked 7-day schedule from up to 4 weeks. It formats this massive payload into a highly professional, well-styled HTML email document that the patient can export directly to their personal inbox to share with real-world doctors.
"""

from pydantic import BaseModel, Field

class EmailDraftSchema(BaseModel):
    subject_line: str = Field(...)
    html_body: str = Field(..., description="Professional email body using HTML tags. Must include an HTML table grouping ALL completed tasks from ALL tracked weeks.")

def execute_agent_10(client, patient_name: str, is_successful: bool, clinical_payload: str):
    if is_successful:
        system_prompt = f"You are Agent 10, the automated scribe for the 'Aura Wellbeing Team'. Draft a highly professional email to the patient ({patient_name}) summarizing their symptoms, expected conditions, and an HTML table containing ALL completed tasks. Explicitly include the phrase 'You have accomplished all your goals, well done!'. End warmly."
    else:
        system_prompt = f"You are Agent 10, the automated scribe for the 'Aura Wellbeing Team'. Draft a highly professional email to the patient ({patient_name}). The patient did NOT improve. Explicitly include the phrase 'Please share this comprehensive record with a medical professional for further diagnosis.' Do NOT congratulate them."
        
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": clinical_payload}
    ]
    return client.beta.chat.completions.parse(model="gpt-4o-mini", messages=messages, response_format=EmailDraftSchema).choices[0].message.parsed