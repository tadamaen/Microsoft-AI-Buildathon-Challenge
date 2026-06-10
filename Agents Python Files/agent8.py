"""
Agent 8: Discharge Maintenance Coach

Description:
This agent triggers at the end of the patient journey. Depending on whether the user successfully concluded their recovery (severity dropped) or failed out (severity remained high after 4 weeks), this agent provides the final sign-off. It generates either a celebratory long-term habit-maintenance protocol or a serious medical escalation warning.
"""

from pydantic import BaseModel, Field
from typing import List

class MaintenancePlanSchema(BaseModel): 
    congratulations_message: str = Field(...)
    long_term_steps: List[str] = Field(...)

def execute_agent_8(client, is_successful: bool, agent_5_json_payload: str):
    if is_successful:
        system_prompt = "You are Agent 8. Provide maintenance guidance for a patient who has successfully completed their recovery plan."
    else:
        system_prompt = "You are Agent 8. The patient has NOT improved after 4 weeks and requires medical attention. Provide serious next steps focusing on seeking professional medical or psychological help immediately. Use the 'congratulations_message' field to output a serious warning header. Do NOT congratulate them."
        
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": agent_5_json_payload}
    ]
    return client.beta.chat.completions.parse(model="gpt-4o-mini", messages=messages, response_format=MaintenancePlanSchema).choices[0].message.parsed