"""
Agent 7: Adherence Dynamic Rescheduler

Description:
This agent handles failure states gracefully. When a user marks tasks as "Missed" or "Too Hard" in the UI, this agent intercepts the current schedule and the user's feedback. It completely rewrites the 7-day schedule, keeping completed tasks locked in place, but dynamically softening or shifting the missed tasks to ensure the user does not get overwhelmed.
"""

from pydantic import BaseModel, Field
from typing import List
import json

class DailyTask(BaseModel): 
    exact_date: str = Field(...)
    action_item: str = Field(...)

class AdjustedPlanSchema(BaseModel): 
    acknowledgement_note: str = Field(...)
    weekly_schedule: List[DailyTask] = Field(..., min_length=7, max_length=7)

def execute_agent_7(client, current_plan_json: str, user_feedback_dict: dict):
    system_prompt = "You are Agent 7 (Dynamic Rescheduler). Output a FULL 7-day schedule (EXACTLY 7 tasks). Keep 'Completed'/'Pending' tasks identical. Make 'Too Hard'/'Missed' easier. Preserve exact calendar dates."
    user_payload = f"PLAN:\n{current_plan_json}\n\nFEEDBACK:\n{json.dumps(user_feedback_dict)}"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_payload}
    ]
    return client.beta.chat.completions.parse(model="gpt-4o-mini", messages=messages, response_format=AdjustedPlanSchema).choices[0].message.parsed