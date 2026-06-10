"""
Agent 9: Active Adherence Accountability Coach

Description:
This agent operates as a lightweight notification engine. It scans the user's schedule for "Pending" tasks that are due today or tomorrow. It then generates a short, supportive, and customized notification message designed to gently nudge the user to check their dashboard and complete their daily protocol.
"""

from pydantic import BaseModel, Field

class ReminderSchema(BaseModel): 
    greeting_and_reminder: str = Field(...)
    suggested_action: str = Field(...)

def execute_agent_9(client, pending_tasks_json: str):
    system_prompt = "You are Agent 9 (Accountability Coach). Receive a list of pending tasks and write a supportive, concise notification check-in message to encourage timely completion."
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": pending_tasks_json}
    ]
    return client.beta.chat.completions.parse(model="gpt-4o-mini", messages=messages, response_format=ReminderSchema).choices[0].message.parsed