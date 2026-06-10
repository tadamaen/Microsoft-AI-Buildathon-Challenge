"""
Agent 6: Care Plan Micro-Planner

Description:
This agent is the architectural scheduler. Utilizing the translated patient profile from Agent 5, it breaks down the recommended recovery steps into a highly actionable, strict 7-day calendar. It assigns specific action items to exact upcoming dates, acting as the logic engine that powers the user's interactive UI and Google/Outlook Calendar syncs.
"""

from pydantic import BaseModel, Field
from typing import List
from datetime import datetime

class DailyTask(BaseModel): 
    exact_date: str = Field(...)
    action_item: str = Field(...)

class ActionPlanSchema(BaseModel): 
    weekly_schedule: List[DailyTask] = Field(..., min_length=7, max_length=7)
    success_metrics: str = Field(...)
    encouragement_note: str = Field(...)

def execute_agent_6(client, current_start_date: datetime, agent_5_json_payload: str):
    system_prompt = "You are Agent 6 (Micro-Planner). Decompose recovery steps using exact calendar dates. You MUST create EXACTLY 7 tasks (1 per day for 7 consecutive days)."
    today_str = current_start_date.strftime("%A, %B %d, %Y")
    user_payload = f"START DATE REFERENCE: {today_str}\n\nPATIENT PROFILE SUMMARY:\n{agent_5_json_payload}"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_payload}
    ]
    return client.beta.chat.completions.parse(model="gpt-4o-mini", messages=messages, response_format=ActionPlanSchema).choices[0].message.parsed