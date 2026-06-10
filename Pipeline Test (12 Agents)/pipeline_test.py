import os
import json
import streamlit as st
from datetime import datetime
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import List, Optional, Literal

# ==========================================
# 1. INITIALIZE OPENAI CLIENT
# ==========================================
# Make sure to replace this placeholder string with your live API key
openai_api_key = "YOUR OPENAI_API_KEY_HERE"                     # Replace with your actual OpenAI API key
microsoft_client_id = "YOUR_MICROSOFT_CLIENT_ID_HERE"           # Replace with your actual Microsoft Client ID
client = OpenAI(api_key=openai_api_key)

st.set_page_config(page_title="12-Agent Testing Harness", page_icon="⚙️", layout="wide")

# ==========================================
# 2. DEFINE STRUCTURAL SCHEMAS FOR ALL AGENTS
# ==========================================
class ClinicalIntakeSchema(BaseModel):
    primary_concerns: List[str] = Field(...)
    symptom_duration: Optional[str] = Field(None)
    severity_scale: Optional[int] = Field(None)
    physical_indicators: List[str] = Field(default=[])
    emotional_indicators: List[str] = Field(default=[])
    contextual_triggers: List[str] = Field(default=[])
    is_information_complete: bool = Field(...)
    missing_fields_rationale: Optional[str] = Field(None)

class TriageClassification(BaseModel):
    routing_decision: Literal["ROUTE_TO_PHYSICAL_RAG", "ROUTE_TO_MENTAL_RAG", "ROUTE_TO_INTERSECTION_RAG", "ROUTE_TO_INTAKE_LOOP"] = Field(...)
    physical_flags_present: bool = Field(...)
    mental_flags_present: bool = Field(...)
    comorbidity_detected: bool = Field(...)
    is_data_sufficient: bool = Field(...)
    clinical_reasoning: str = Field(...)

class RawRAGContextSchema(BaseModel): 
    retrieved_literature: str = Field(...)

class TriageSynthesisSchema(BaseModel): 
    potential_conditions: List[str] = Field(...)
    underlying_mechanisms: str = Field(...)
    recommended_next_steps: List[str] = Field(...)

class PatientCommunicationSchema(BaseModel): 
    empathetic_summary: str = Field(...)
    understanding_the_why: str = Field(...)
    gentle_next_steps: List[str] = Field(...)

class DailyTask(BaseModel): 
    exact_date: str = Field(...)
    action_item: str = Field(...)

class ActionPlanSchema(BaseModel): 
    weekly_schedule: List[DailyTask] = Field(..., min_length=7, max_length=7)
    success_metrics: str = Field(...)
    encouragement_note: str = Field(...)

class AdjustedPlanSchema(BaseModel): 
    acknowledgement_note: str = Field(...)
    weekly_schedule: List[DailyTask] = Field(..., min_length=7, max_length=7)

class MaintenancePlanSchema(BaseModel): 
    congratulations_message: str = Field(...)
    long_term_steps: List[str] = Field(...)

class ReminderSchema(BaseModel): 
    greeting_and_reminder: str = Field(...)
    suggested_action: str = Field(...)

class EmailDraftSchema(BaseModel):
    subject_line: str = Field(...)
    html_body: str = Field(...)

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

class CheckInAnalysisSchema(BaseModel):
    estimated_severity: int = Field(...)
    analysis_rationale: str = Field(...)

# Helper function to invoke Structured Outputs Engine
def run_agent(model_schema, system_prompt: str, user_payload: str):
    return client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_payload}
        ],
        response_format=model_schema
    ).choices[0].message.parsed

# ==========================================
# 3. CORE DIAGNOSTIC LAYOUT SETUP
# ==========================================
st.title("⚙️ End-to-End 12-Agent Automated Diagnostics Suite")
st.write("This diagnostic pipeline lets you isolate and evaluate the output of all 12 operational sub-agents inside the core application engine framework sequentially.")
st.markdown("---")

# Standardized baseline test case string matching your precise trial scenario parameters
test_case_scenario = (
    "I have been feeling incredibly burned out and overwhelmed for the last 3 months. "
    "I recently got a promotion at work and my new manager is extremely demanding, which is triggering all of this stress. "
    "Emotionally, I am having panic attacks, feeling a constant sense of dread, and I find myself crying for no reason. "
    "Physically, I have chronic tension headaches, my stomach is always in knots, and I am suffering from severe insomnia. "
    "If I had to rate my distress right now, it is an 8 out of 10. I just need some help figuring out what to do."
)

scenario_input = st.text_area("🔧 Scenario Baseline Payload Vector Target:", value=test_case_scenario, height=150)

if st.button("🚀 Execute Sequential 12-Agent Diagnostics Sequence"):
    if scenario_input.strip():
        
        # ---------------------------------------------------------
        # AGENT 1: Clinical Intake (Parser Layer)
        # ---------------------------------------------------------
        st.markdown("### 🟢 Agent 1: Clinical Intake Parser")
        with st.spinner("Executing Agent 1 analysis..."):
            a1_prompt = "You are Agent 1 (Clinical Intake Parser). Read the user query and cleanly decompose all explicitly listed or implied physiological, environmental, and mental conditions."
            a1_out = run_agent(ClinicalIntakeSchema, a1_prompt, scenario_input)
            
            with st.expander("👁️ View Agent 1 Structured Object Payload", expanded=True):
                st.json(a1_out.model_dump())
            st.success("✅ Agent 1 Diagnostics Completed Successfully!")
        st.markdown("---")

        # ---------------------------------------------------------
        # AGENT 2: Triage Classifier (Router Layer)
        # ---------------------------------------------------------
        st.markdown("### 🔵 Agent 2: Triage Decision Classifier")
        with st.spinner("Executing Agent 2 analysis..."):
            a2_prompt = "You are Agent 2 (Triage Decision Classifier). Take the structured clinical intake data and select an internal routing lane target for documentation lookups."
            a2_out = run_agent(TriageClassification, a2_prompt, a1_out.model_dump_json())
            
            with st.expander("👁️ View Agent 2 Structured Object Payload", expanded=True):
                st.json(a2_out.model_dump())
            st.success("✅ Agent 2 Diagnostics Completed Successfully!")
        st.markdown("---")

        # ---------------------------------------------------------
        # AGENT 3: Raw RAG Retriever (Mock Knowledge Injection)
        # ---------------------------------------------------------
        st.markdown("### 🟣 Agent 3: Raw Knowledge Base Vector Retriever")
        with st.spinner("Executing Agent 3 data collection..."):
            a3_prompt = "You are Agent 3 (RAG Context Knowledge Injector). Based on the chosen triage routing decision, output a collection of valid parameters, guidelines, and definitions to assist downstream diagnostic synthesizers."
            a3_out = run_agent(RawRAGContextSchema, a3_prompt, a2_out.model_dump_json())
            
            with st.expander("👁️ View Agent 3 Output Text Data Block", expanded=True):
                st.write(a3_out.retrieved_literature)
            st.success("✅ Agent 3 Diagnostics Completed Successfully!")
        st.markdown("---")

        # ---------------------------------------------------------
        # AGENT 4: Triage Synthesizer (Clinical Analysis)
        # ---------------------------------------------------------
        st.markdown("### 🟠 Agent 4: Clinical Triage Diagnostic Synthesizer")
        with st.spinner("Executing Agent 4 clinical cross-examination..."):
            a4_prompt = "You are Agent 4 (Triage Diagnostic Synthesizer). Cross-reference raw symptoms with standard knowledge guidelines to generate expected diagnostic considerations and mechanical etiologies."
            a4_payload = f"SYMPTOMS:\n{a1_out.model_dump_json()}\n\nGUIDELINES:\n{a3_out.retrieved_literature}"
            a4_out = run_agent(TriageSynthesisSchema, a4_prompt, a4_payload)
            
            with st.expander("👁️ View Agent 4 Structured Object Payload", expanded=True):
                st.json(a4_out.model_dump())
            st.success("✅ Agent 4 Diagnostics Completed Successfully!")
        st.markdown("---")

        # ---------------------------------------------------------
        # AGENT 5: Patient Communicator (Translation Layer)
        # ---------------------------------------------------------
        st.markdown("### 🔴 Agent 5: Patient Translation Communicator")
        with st.spinner("Executing Agent 5 linguistic mapping..."):
            a5_prompt = "You are Agent 5 (Patient Translation Communicator). Rephrase complex physiological and diagnostic mechanics into safe, empathetic, patient-friendly communication."
            a5_out = run_agent(PatientCommunicationSchema, a5_prompt, a4_out.model_dump_json())
            
            with st.expander("👁️ View Agent 5 Structured Object Payload", expanded=True):
                st.json(a5_out.model_dump())
            st.success("✅ Agent 5 Diagnostics Completed Successfully!")
        st.markdown("---")

        # ---------------------------------------------------------
        # AGENT 6: Micro-Planner (Decomposition Execution Engine)
        # ---------------------------------------------------------
        st.markdown("### 🟡 Agent 6: Care Plan Micro-Planner")
        with st.spinner("Executing Agent 6 care plan blueprint scheduling..."):
            a6_prompt = "You are Agent 6 (Micro-Planner). Take the patient data and split recommendations into an exact 7-day action protocol block using consecutive dates."
            today_str = datetime.now().strftime("%A, %B %d, %Y")
            a6_payload = f"START DATE REFERENCE: {today_str}\n\nPATIENT PROFILE SUMMARY:\n{a5_out.model_dump_json()}"
            a6_out = run_agent(ActionPlanSchema, a6_prompt, a6_payload)
            
            with st.expander("👁️ View Agent 6 Structured Object Payload", expanded=True):
                st.json(a6_out.model_dump())
            st.success("✅ Agent 6 Diagnostics Completed Successfully!")
        st.markdown("---")

        # ---------------------------------------------------------
        # AGENT 7: Dynamic Rescheduler (Adherence Optimization)
        # ---------------------------------------------------------
        st.markdown("### 🔄 Agent 7: Adherence Dynamic Rescheduler")
        with st.spinner("Simulating task failure to trigger Agent 7 recalibration..."):
            a7_prompt = "You are Agent 7 (Dynamic Rescheduler). Read an existing care plan along with user execution tracking comments. Re-draft and balance tasks to make missed days easier."
            mock_user_feedback = '{"Day 1": "✅ Completed", "Day 2": "🏔️ Too Hard - Need an easier option"}'
            a7_payload = f"CURRENT PROGRAM:\n{a6_out.model_dump_json()}\n\nTRACKING FEEDBACK LOGS:\n{mock_user_feedback}"
            a7_out = run_agent(AdjustedPlanSchema, a7_prompt, a7_payload)
            
            with st.expander("👁️ View Agent 7 Recalibration Object Payload", expanded=True):
                st.json(a7_out.model_dump())
            st.success("✅ Agent 7 Diagnostics Completed Successfully!")
        st.markdown("---")

        # ---------------------------------------------------------
        # AGENT 8: Maintenance Coach (Discharge Protocol)
        # ---------------------------------------------------------
        st.markdown("### 🏆 Agent 8: Discharge Maintenance Coach")
        with st.spinner("Executing Agent 8 long-term protocol routing..."):
            a8_prompt = "You are Agent 8 (Discharge Maintenance Coach). Based on patient history, design actionable long-term lifestyle habits to prevent baseline symptoms from re-triggering."
            a8_out = run_agent(MaintenancePlanSchema, a8_prompt, a5_out.model_dump_json())
            
            with st.expander("👁️ View Agent 8 Long-Term Protocol Object Payload", expanded=True):
                st.json(a8_out.model_dump())
            st.success("✅ Agent 8 Diagnostics Completed Successfully!")
        st.markdown("---")

        # ---------------------------------------------------------
        # AGENT 9: Accountability Coach (Real-Time Tracker)
        # ---------------------------------------------------------
        st.markdown("### 🔔 Agent 9: Active Adherence Accountability Coach")
        with st.spinner("Simulating overdue tasks to trigger Agent 9 notifications..."):
            a9_prompt = "You are Agent 9 (Accountability Coach). Receive a list of pending tasks and write a supportive, concise notification check-in message to encourage timely completion."
            mock_overdue_payload = '[{"exact_date": "Tomorrow", "action_item": "Perform deep breathing exercises for 10 minutes"}]'
            a9_out = run_agent(ReminderSchema, a9_prompt, mock_overdue_payload)
            
            with st.expander("👁️ View Agent 9 Accountability Message Object", expanded=True):
                st.json(a9_out.model_dump())
            st.success("✅ Agent 9 Diagnostics Completed Successfully!")
        st.markdown("---")

        # ---------------------------------------------------------
        # AGENT 10: Professional Email Crafter (Scribe Node)
        # ---------------------------------------------------------
        st.markdown("### 📧 Agent 10: Medical Record Scribe & Email Crafter")
        with st.spinner("Executing Agent 10 automated document drafting..."):
            a10_prompt = "You are Agent 10 (Email Crafter). Draft a highly professional medical log document written cleanly inside structured HTML formatting wrappers."
            a10_payload = f"INITIAL ASSESSMENT:\n{a1_out.model_dump_json()}\n\nWEEKLY RECOVERY METRICS:\n{a6_out.model_dump_json()}"
            a10_out = run_agent(EmailDraftSchema, a10_prompt, a10_payload)
            
            with st.expander("👁️ View Agent 10 Generated Document Object Payload", expanded=True):
                st.json(a10_out.model_dump())
            st.success("✅ Agent 10 Diagnostics Completed Successfully!")
        st.markdown("---")

        # ---------------------------------------------------------
        # AGENT 11: News Collater (Database Aggregator)
        # ---------------------------------------------------------
        st.markdown("### 📰 Agent 11: Medical Database News Feed Collater")
        with st.spinner("Executing Agent 11 query mapping..."):
            a11_prompt = "You are Agent 11 (News Collater). Take a list of conditions and symptoms, select highly relevant articles matching that clinical spectrum, and map them to standard formats."
            
            # Simple dummy source database vector framework
            mock_news_db = '[{"topic": "Anxiety & Stress", "description": "Manage stress patterns", "source": "Healthline", "url": "https://example.com/stress", "image": "https://example.com/img.png"}]'
            a11_payload = f"DATABASE SPECTRA:\n{mock_news_db}\n\nPATIENT PROFILE SYMPTOMS:\n{a1_out.model_dump_json()}"
            a11_out = run_agent(NewsCollaterSchema, a11_prompt, a11_payload)
            
            with st.expander("👁️ View Agent 11 News Feed Object Payload", expanded=True):
                st.json(a11_out.model_dump())
            st.success("✅ Agent 11 Diagnostics Completed Successfully!")
        st.markdown("---")

        # ---------------------------------------------------------
        # AGENT 12: Check-In Sentiment Analyzer (NLP Evaluator)
        # ---------------------------------------------------------
        st.markdown("### 🔄 Agent 12: Check-In Sentiment Metrics Evaluator")
        with st.spinner("Executing Agent 12 progress evaluation..."):
            a12_prompt = "You are Agent 12 (Check-In Sentiment Analyzer). Read a user's weekly update reflection text and extract an integer-bound index value tracking distress metrics safely."
            mock_reflection = "I'm doing a bit better. The breathing exercises helped a little with the panic, though work is still incredibly stressful. I'm sleeping a little better, but still feel quite burned out."
            a12_out = run_agent(CheckInAnalysisSchema, a12_prompt, mock_reflection)
            
            with st.expander("👁️ View Agent 12 Analytical Metrics Payload", expanded=True):
                st.json(a12_out.model_dump())
            st.success("✅ Agent 12 Diagnostics Completed Successfully!")
        st.markdown("---")

        # Final Suite Execution Notification
        st.success("🏆 Global Sequence Diagnostic Sequence Finalized: All 12 Operational AI Sub-Agents verified successfully!")