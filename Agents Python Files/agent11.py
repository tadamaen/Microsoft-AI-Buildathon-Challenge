"""
Agent 11: Medical Database News Feed Collater

Description:
This agent serves as a highly targeted content recommendation engine. It takes the patient's specific symptoms and potential conditions and searches a predefined JSON database of health literature. It selects exactly 6 articles that directly match the user's needs and writes a custom, single-sentence summary for each, explaining exactly why reading it will help their specific case.
"""

from pydantic import BaseModel, Field
from typing import List
import json

class NewsArticleSchema(BaseModel):
    headline: str = Field(...)
    brief_summary: str = Field(...)
    credible_source: str = Field(...)
    reading_time_minutes: int = Field(...)
    article_url: str = Field(...)
    image_url: str = Field(...)

class NewsCollaterSchema(BaseModel):
    encouraging_intro: str = Field(...)
    curated_articles: List[NewsArticleSchema] = Field(..., min_length=6, max_length=6)

def execute_agent_11(client, database_json: str, patient_conditions: str, patient_symptoms: str):
    system_prompt = "You are Agent 11, a Health News Collater. Read the USER CONDITIONS and SYMPTOMS. Then, select EXACTLY 6 articles from the provided JSON DATABASE that best match the user's situation. For each, write a custom 'brief_summary' explaining why it helps them."
    user_payload = f"DATABASE: {database_json}\n\nUSER CONDITIONS: {patient_conditions}\nUSER SYMPTOMS: {patient_symptoms}"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_payload}
    ]
    return client.beta.chat.completions.parse(model="gpt-4o-mini", messages=messages, response_format=NewsCollaterSchema).choices[0].message.parsed