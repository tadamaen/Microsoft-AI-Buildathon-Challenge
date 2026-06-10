"""
Agent 3: Raw Knowledge Base Vector Retriever

Description:
This agent simulates a connection to a medical vector database. Based on the routing decision determined by Agent 2 and the raw symptoms mapped by Agent 1, it "retrieves" the highly specific, unformatted clinical literature, parameters, and guidelines required to accurately assess the patient's state. 
"""

from pydantic import BaseModel, Field

class RawRAGContextSchema(BaseModel): 
    retrieved_literature: str = Field(...)

def execute_agent_3(client, routing_decision: str, agent_1_json_payload: str):
    system_prompt = f"You are Agent 3 (RAG Context Knowledge Injector). Based on the chosen triage routing decision ({routing_decision}), output a collection of valid medical parameters, clinical guidelines, and definitions to assist downstream diagnostic synthesizers."
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": agent_1_json_payload}
    ]
    return client.beta.chat.completions.parse(model="gpt-4o-mini", messages=messages, response_format=RawRAGContextSchema).choices[0].message.parsed