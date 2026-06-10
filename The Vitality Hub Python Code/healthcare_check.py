import os
import json
import requests
import base64
import urllib.parse
import time
import PyPDF2
import pandas as pd
import altair as alt
import streamlit as st
import pytz
from datetime import datetime, timedelta
from email.message import EmailMessage
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import List, Optional, Literal

# --- GOOGLE API IMPORTS ---
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# --- MICROSOFT GRAPH API IMPORTS ---
import msal

# ==========================================
# 1. DEFINE SCHEMAS (AGENT OUTPUT STRUCTURES)
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

class RawRAGContextSchema(BaseModel): retrieved_literature: str = Field(...)
class TriageSynthesisSchema(BaseModel): potential_conditions: List[str] = Field(...); underlying_mechanisms: str = Field(...); recommended_next_steps: List[str] = Field(...)
class PatientCommunicationSchema(BaseModel): empathetic_summary: str = Field(...); understanding_the_why: str = Field(...); gentle_next_steps: List[str] = Field(...)

class DailyTask(BaseModel): exact_date: str = Field(...); action_item: str = Field(...)
class ActionPlanSchema(BaseModel): weekly_schedule: List[DailyTask] = Field(..., min_length=7, max_length=7); success_metrics: str = Field(...); encouragement_note: str = Field(...)
class AdjustedPlanSchema(BaseModel): acknowledgement_note: str = Field(...); weekly_schedule: List[DailyTask] = Field(..., min_length=7, max_length=7)
class MaintenancePlanSchema(BaseModel): congratulations_message: str = Field(...); long_term_steps: List[str] = Field(...)
class ReminderSchema(BaseModel): greeting_and_reminder: str = Field(...); suggested_action: str = Field(...)

class EmailDraftSchema(BaseModel):
    subject_line: str = Field(...)
    html_body: str = Field(..., description="Professional email body using HTML tags. Must include: 1. A summary of initial problems. 2. A single comprehensive HTML table grouping ALL the completed tasks from ALL tracked weeks. 3. A congratulatory or warning message based on the prompt instructions. 4. A list of 'Recommended next steps'.")

class NewsArticleSchema(BaseModel):
    headline: str = Field(..., description="A custom, catchy headline related to the user's issue.")
    brief_summary: str = Field(..., description="A 1-sentence engaging summary or fun fact explaining why this helps them.")
    credible_source: str = Field(...)
    reading_time_minutes: int = Field(...)
    article_url: str = Field(...)
    image_url: str = Field(...)

class NewsCollaterSchema(BaseModel):
    encouraging_intro: str = Field(...)
    curated_articles: List[NewsArticleSchema] = Field(..., min_length=6, max_length=6, description="Exactly 6 highly relevant articles.")

class CheckInAnalysisSchema(BaseModel):
    estimated_severity: int = Field(..., description="Estimate the user's current severity level from 0 to 10 based purely on their textual update.")
    analysis_rationale: str = Field(...)

# ==========================================
# 2. INITIALIZE CLIENTS & SESSION STATE
# ==========================================
openai_api_key = "YOUR OPENAI_API_KEY HERE"                         # Replace with your actual OpenAI API key
microsoft_client_id = "YOUR MICROSOFT CLIENT ID HERE"               # Replace with your actual Microsoft Azure AD application client ID

client = OpenAI(api_key=openai_api_key)

st.set_page_config(page_title="The Vitality Hub", page_icon="✨", layout="wide")

if "pipeline_done" not in st.session_state:
    st.session_state.pipeline_done = False
    st.session_state.wants_schedule = False
    for k in ["a1_res", "a4_res", "a5_res", "a6_res", "a8_res", "a10_res", "a11_res", "a12_res", "halt_msg"]:
        st.session_state[k] = None
    st.session_state.task_feedback = {}
    st.session_state.plan_version = 1 
    st.session_state.calendar_synced = False
    st.session_state.calendar_events = {}  
    st.session_state.all_created_events = [] 
    st.session_state.user_email = ""
    st.session_state.user_name = "" 
    st.session_state.calendar_platform = None
    st.session_state.balloons_shown = False
    
    # State tracking for multi-week progression & Data Export
    st.session_state.initial_severity = None
    st.session_state.cycle_count = 1
    st.session_state.current_start_date = datetime.now()
    st.session_state.historical_schedules = []
    st.session_state.view_maintenance = False
    st.session_state.is_successful_conclusion = False
    
    # Research Logging States
    st.session_state.initial_message = ""
    st.session_state.possible_symptoms = ""
    st.session_state.weekly_messages = []
    st.session_state.severities = []
    st.session_state.consent_given = None
    st.session_state.data_exported = False

def format_list(items):
    return "".join([f"<li>{item}</li>" for item in items]) if items else "<li>None specified</li>"

# 📚 CURATED HEALTH DATABASE 
CURATED_HEALTH_DATABASE = [
    {"topic": "Anxiety & Stress", "description": "Learn effective strategies to manage everyday stress and reduce anxiety symptoms naturally.", "source": "Healthline", "url": "https://www.healthline.com/health/anxiety", "image": "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=400&q=80"},
    {"topic": "Sleep Hygiene & Insomnia", "description": "Discover proven bedtime routines and environmental tweaks to cure insomnia and improve sleep quality.", "source": "Sleep Foundation", "url": "https://www.sleepfoundation.org/sleep-hygiene", "image": "https://images.unsplash.com/photo-1541781774459-bb2af2f05b55?w=400&q=80"},
    {"topic": "Burnout & Exhaustion", "description": "Recognize the signs of professional burnout and explore actionable steps toward recovery.", "source": "Mayo Clinic", "url": "https://www.mayoclinic.org/healthy-lifestyle/adult-health/in-depth/burnout/art-20046642", "image": "https://images.unsplash.com/photo-1499951360447-b19be8fe80f5?w=400&q=80"},
    {"topic": "Tension Headaches", "description": "Identify common triggers for tension headaches and learn quick, effective relief techniques.", "source": "WebMD", "url": "https://www.webmd.com/migraines-headaches/tension-headaches", "image": "https://images.unsplash.com/photo-1505576399279-565b52d4ac71?w=400&q=80"},
    {"topic": "Mental Health & Exercise", "description": "Understand the powerful connection between physical activity and improved psychological well-being.", "source": "HelpGuide", "url": "https://www.helpguide.org/articles/healthy-living/the-mental-health-benefits-of-exercise.htm", "image": "https://images.unsplash.com/photo-1476480862126-209bfaa8edc8?w=400&q=80"},
    {"topic": "Nutritional Psychiatry", "description": "Explore how your diet directly impacts your mood, energy levels, and brain function.", "source": "Harvard Health", "url": "https://www.health.harvard.edu/blog/nutritional-psychiatry-your-brain-on-food-201511168626", "image": "https://images.unsplash.com/photo-1490645935967-10de6ba17061?w=400&q=80"},
    {"topic": "Mindfulness & Meditation", "description": "A beginner's guide to practicing mindfulness to ground yourself and reduce mental clutter.", "source": "Mindful", "url": "https://www.mindful.org/meditation/mindfulness-getting-started/", "image": "https://images.unsplash.com/photo-1508672019048-805c876b67e2?w=400&q=80"},
    {"topic": "Journaling for Health", "description": "Unlock the therapeutic benefits of expressive writing to process complex emotions.", "source": "URMC", "url": "https://www.urmc.rochester.edu/encyclopedia/content.aspx?ContentID=4552&ContentTypeID=1", "image": "https://images.unsplash.com/photo-1506784983877-45594efa4cbe?w=400&q=80"},
    {"topic": "Neck & Back Pain", "description": "Simple, effective posture corrections and exercises to alleviate chronic spine and neck discomfort.", "source": "Spine-Health", "url": "https://www.spine-health.com/conditions/neck-pain/neck-pain-symptoms", "image": "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=400&q=80"},
    {"topic": "Hydration Benefits", "description": "Learn exactly how water intake influences your physical energy and mental clarity.", "source": "Mayo Clinic", "url": "https://www.mayoclinic.org/healthy-lifestyle/nutrition-and-healthy-eating/in-depth/water/art-20044256", "image": "https://images.unsplash.com/photo-1523362628745-0c100150b504?w=400&q=80"},
    {"topic": "Digital Detox", "description": "Practical tips to unplug from screens, reduce eye strain, and reclaim your mental focus.", "source": "Verywell Mind", "url": "https://www.verywellmind.com/why-and-how-to-do-a-digital-detox-4771321", "image": "https://images.unsplash.com/photo-1512941937669-90a1b58e7e9c?w=400&q=80"},
    {"topic": "Breathing Exercises", "description": "Master deep breathing techniques to instantly lower your heart rate and calm your nervous system.", "source": "Healthline", "url": "https://www.healthline.com/health/breathing-exercise", "image": "https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=400&q=80"},
    {"topic": "Time Management", "description": "Regain control of your schedule to lower daily stress and prevent task overload.", "source": "HBR", "url": "https://hbr.org/2020/01/time-management-is-about-more-than-life-hacks", "image": "https://images.unsplash.com/photo-1434494878577-86c23bcb06b9?w=400&q=80"},
    {"topic": "Work-Life Balance", "description": "Establish healthy boundaries between your career and personal life to sustain long-term wellbeing.", "source": "MHA National", "url": "https://www.mhanational.org/work-life-balance", "image": "https://images.unsplash.com/photo-1498050108023-c5249f4df085?w=400&q=80"},
    {"topic": "Desk Stretches", "description": "Quick, discreet exercises you can do at your desk to prevent stiffness and boost circulation.", "source": "Healthline", "url": "https://www.healthline.com/health/deskercise", "image": "https://images.unsplash.com/photo-1517048676732-d65bc937f952?w=400&q=80"}
]

# ==========================================
# 3. LIVE GOOGLE API ENGINE (CALENDAR + GMAIL)
# ==========================================
SCOPES_GOOGLE = ['https://www.googleapis.com/auth/calendar.events', 'https://www.googleapis.com/auth/gmail.send']
def get_google_credentials():
    creds = None
    if os.path.exists('token.json'): creds = Credentials.from_authorized_user_file('token.json', SCOPES_GOOGLE)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token: creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES_GOOGLE)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token: token.write(creds.to_json())
    return creds

def parse_flexible_date(date_str: str) -> datetime:
    for fmt in ["%A, %B %d, %Y", "%Y-%m-%d", "%B %d, %Y", "%A, %d %B %Y", "%m/%d/%Y"]:
        try: return datetime.strptime(date_str.strip(), fmt)
        except ValueError: continue
    return datetime.now()

def production_create_calendar_event(email: str, task: DailyTask) -> str:
    service = build('calendar', 'v3', credentials=get_google_credentials())
    date_obj = parse_flexible_date(task.exact_date)
    hour = 9 
    start_time = pytz.timezone('Asia/Singapore').localize(date_obj.replace(hour=hour))
    event = {'summary': f"Care Plan: {task.action_item}", 'start': {'dateTime': start_time.isoformat()}, 'end': {'dateTime': (start_time + timedelta(hours=1)).isoformat()}, 'attendees': [{'email': email}]}
    return service.events().insert(calendarId='primary', body=event).execute().get('id')

def production_update_calendar_event(event_id: str, email: str, task: DailyTask):
    service = build('calendar', 'v3', credentials=get_google_credentials())
    event = service.events().get(calendarId='primary', eventId=event_id).execute()
    event['summary'] = f"Care Plan (Adjusted): {task.action_item}"
    service.events().update(calendarId='primary', eventId=event_id, body=event).execute()

def production_delete_calendar_event(event_id: str):
    try: build('calendar', 'v3', credentials=get_google_credentials()).events().delete(calendarId='primary', eventId=event_id).execute()
    except Exception: pass 

def send_real_gmail(user_email: str, agent_10_draft: EmailDraftSchema):
    service = build('gmail', 'v1', credentials=get_google_credentials())
    message = EmailMessage()
    clean_html = agent_10_draft.html_body.replace("```html", "").replace("```", "").strip()
    message.set_content(clean_html, subtype='html')
    message['To'] = user_email
    message['From'] = "me" 
    message['Subject'] = agent_10_draft.subject_line
    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId="me", body={'raw': encoded_message}).execute()

# ==========================================
# 3.5 LIVE MICROSOFT GRAPH API ENGINE (OUTLOOK)
# ==========================================
SCOPES_MS = ["Calendars.ReadWrite", "Mail.Send"]
MS_AUTHORITY = "https://login.microsoftonline.com/common"

def get_ms_headers():
    cache = msal.SerializableTokenCache()
    if os.path.exists("token_ms.json"):
        with open("token_ms.json", "r") as f: cache.deserialize(f.read())
    app = msal.PublicClientApplication(microsoft_client_id, authority=MS_AUTHORITY, token_cache=cache)
    accounts = app.get_accounts()
    result = app.acquire_token_silent(SCOPES_MS, account=accounts[0]) if accounts else None
    if not result: result = app.acquire_token_interactive(scopes=SCOPES_MS)
    if "access_token" in result:
        with open("token_ms.json", "w") as f: f.write(cache.serialize())
        return {"Authorization": f"Bearer {result['access_token']}", "Content-Type": "application/json"}
    st.stop()

def production_create_outlook_event(email: str, task: DailyTask) -> str:
    headers = get_ms_headers()
    date_obj = parse_flexible_date(task.exact_date)
    hour = 9 
    start_time = date_obj.replace(hour=hour).isoformat()
    end_time = (date_obj.replace(hour=hour) + timedelta(hours=1)).isoformat()
    event_data = {"subject": f"Care Plan: {task.action_item}", "start": {"dateTime": start_time, "timeZone": "Asia/Singapore"}, "end": {"dateTime": end_time, "timeZone": "Asia/Singapore"}, "attendees": [{"emailAddress": {"address": email}, "type": "required"}]}
    return requests.post("https://graph.microsoft.com/v1.0/me/events", headers=headers, json=event_data).json().get("id")

def production_update_outlook_event(event_id: str, email: str, task: DailyTask):
    requests.patch(f"https://graph.microsoft.com/v1.0/me/events/{event_id}", headers=get_ms_headers(), json={"subject": f"Care Plan (Adjusted): {task.action_item}"})

def production_delete_outlook_event(event_id: str):
    requests.delete(f"https://graph.microsoft.com/v1.0/me/events/{event_id}", headers=get_ms_headers())

def send_real_outlook_email(user_email: str, agent_10_draft: EmailDraftSchema):
    headers = get_ms_headers()
    clean_html = agent_10_draft.html_body.replace("```html", "").replace("```", "").strip()
    email_data = {
        "message": {
            "subject": agent_10_draft.subject_line,
            "body": {
                "contentType": "HTML",
                "content": clean_html
            },
            "toRecipients": [{"emailAddress": {"address": user_email}}]
        },
        "saveToSentItems": "true"
    }
    requests.post("https://graph.microsoft.com/v1.0/me/sendMail", headers=headers, json=email_data)

# ==========================================
# 4. AGENT EXECUTION & ADVANCED CSS STYLING
# ==========================================
st.markdown("""
<style>
    /* Main Background */
    .stApp, [data-testid='stAppViewContainer'] { 
        background-image: linear-gradient(rgba(255, 255, 255, 0.85), rgba(255, 255, 255, 0.85)), url("https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?q=80&w=2070&auto=format&fit=crop");
        background-size: cover; background-position: center; background-attachment: fixed;
    }
    p, label, div[data-testid='stMarkdownContainer'] { color: #2D3748 !important; }
    h1, h3, h4 { color: #2C4A3E !important; font-family: 'Georgia', serif; }
    .stTextArea textarea { background-color: #FFF0F0 !important; border-radius: 8px; border: 2px solid #FF0000 !important; color: #2D3748 !important; }
    hr.day-divider { border: 0; border-top: 1px solid #D1D5DB; margin: 12px 0; }
    [data-testid="stVerticalBlockBorderWrapper"], fieldset { background-color: #FFF9E6 !important; border: 2px solid #F6E05E !important; border-radius: 15px !important; padding: 15px !important; }
    
    /* Email Table Styling */
    .email-container table { width: 100%; border-collapse: collapse; margin-top: 10px; margin-bottom: 20px; }
    .email-container th { background-color: #EDF2F7; padding: 10px; border: 1px solid #CBD5E0; text-align: left; color: #2D3748; }
    .email-container td { padding: 10px; border: 1px solid #CBD5E0; color: #4A5568; }

    /* --- UNIVERSAL BUTTON STYLING --- */
    .stButton > button, div[data-testid="stButton"] > button {
        background-color: #EDF2F7 !important;
        color: #2D3748 !important;
        border: 1px solid #CBD5E0 !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
    }
    .stButton > button:hover, div[data-testid="stButton"] > button:hover {
        border-color: #2B6CB0 !important;
        color: #2B6CB0 !important;
        background-color: #E2E8F0 !important;
    }

    /* --- FILE UPLOADER & INPUTS DARK MODE OVERRIDE --- */
    .stTextInput input, .stTextArea textarea {
        background-color: #FFFFFF !important;
        color: #2D3748 !important;
        border: 1px solid #CBD5E0 !important;
        border-radius: 8px;
    }
    [data-testid="stFileUploadDropzone"] {
        background-color: #FFFFFF !important;
        color: #2D3748 !important;
        border: 2px dashed #A0AEC0 !important;
    }
    [data-testid="stFileUploadDropzone"] div[data-testid="stMarkdownContainer"] p,
    [data-testid="stFileUploadDropzone"] small {
        color: #2D3748 !important;
    }
    [data-testid="stFileUploadDropzone"] svg {
        fill: #2D3748 !important;
        color: #2D3748 !important;
    }
    
    /* Selectboxes */
    div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        color: #2D3748 !important;
        border: 1px solid #CBD5E0 !important;
    }
    div[data-baseweb="select"] span { color: #2D3748 !important; }

    /* --- SIDEBAR REALIGNMENT & WHITE TEXT ENGINE --- */
    [data-testid="stSidebar"] {
        min-width: 320px !important;
        max-width: 320px !important;
        background-color: #3E2723 !important;
        background-image: radial-gradient(rgba(255,255,255,0.08) 2px, transparent 2px) !important;
        background-size: 20px 20px !important;
        overflow-x: hidden !important; 
    }
    [data-testid="stSidebarResizer"] {
        display: none !important;
    }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] p {
        color: #F7FAFC !important;
    }
    
    /* Strip native structures from padding constraints */
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label > div:first-of-type {
        display: none !important;
        width: 0px !important;
        margin: 0px !important;
        padding: 0px !important;
        position: absolute !important;
    }
    [data-testid="stSidebar"] div.stRadio {
        padding: 0 !important; margin: 0 !important; width: 100% !important;
    }
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] {
        display: flex !important;
        flex-direction: column !important;
        align-items: center !important;
        width: 100% !important;
        gap: 15px !important; 
    }
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label {
        width: 100% !important;
        background-color: transparent !important;
        padding: 6px 0px !important;
        margin: 0 !important;
        cursor: pointer;
        display: flex !important;
        justify-content: center !important;
        align-items: center !important;
        border: none !important;
        box-shadow: none !important;
    }
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label div[data-testid="stMarkdownContainer"] {
        width: 100% !important;
        display: flex !important;
        justify-content: center !important;
        align-items: center !important;
    }
    
    /* Strict white text configuration with an increased horizontal optical translation */
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label p {
        font-size: 17px !important; 
        font-weight: bold !important;
        color: #FFFFFF !important; 
        margin: 0 !important;
        text-align: left !important;
        width: 100% !important;
        white-space: nowrap !important;
        transition: 0.2s;
        transform: translateX(55px) !important;
    }
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label:hover p {
        color: #D69E2E !important;
    }
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label[data-checked="true"],
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label[aria-checked="true"] {
        background-color: transparent !important;
    }
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label[data-checked="true"] p,
    [data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label[aria-checked="true"] p {
        color: #D69E2E !important; 
    }
</style>
""", unsafe_allow_html=True)

def run_agent(model_schema, system_prompt: str, user_payload: str):
    return client.beta.chat.completions.parse(model="gpt-4o-mini", messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_payload}], response_format=model_schema).choices[0].message.parsed


# ==========================================
# 5. SIDEBAR NAVIGATION ROUTER
# ==========================================
st.sidebar.markdown("<h1 style='text-align: center; color: white; margin-bottom: 5px;'>The Vitality Hub</h1>", unsafe_allow_html=True)

logo_col1, logo_col2, logo_col3 = st.sidebar.columns([1, 2.5, 1])
with logo_col2:
    try: st.image("logo.png", width="stretch")
    except: pass 

st.sidebar.markdown("<br>", unsafe_allow_html=True)

page = st.sidebar.radio("Navigation Menu", ["Chat With Us", "Newsfeed", "My Health Insights", "Emergency Contacts"], label_visibility="collapsed")

st.sidebar.markdown("""
<div style="text-align: center; color: #A0AEC0; font-size: 16px; white-space: nowrap; margin-top: 40px; font-weight: bold;">
    Curated By The Aura Wellbeing Team
</div>
""", unsafe_allow_html=True)


# ==========================================
# PAGE 1: CHAT WITH US (CLINICAL INTAKE)
# ==========================================
if page == "Chat With Us":
    st.title("✨ Aura: Your Intelligent Health Sanctuary")

    st.markdown("""
    **Welcome to Aura: Your Intelligent Health Sanctuary!** 🌟 
    We are here to provide a safe, supportive space for you to explore and understand your physical and mental well-being. Aura is designed to bridge the gap between how you feel and the actionable steps needed to feel better, acting as your personal, 24/7 care team.

    To get started, simply share what has been on your mind or body lately. You can type out your symptoms—whether you are dealing with stress, chronic aches, or just feeling 'off'—or securely upload your recent medical notes. Our system will analyze your unique situation to uncover potential underlying conditions and instantly build a personalized, interactive 7-day action plan to guide you toward recovery. 🚀
    """)

    user_input = st.text_area("Share what has been going on lately:", height=160, placeholder="e.g., I've been having tension headaches for the past two weeks...")
    uploaded_file = st.file_uploader("Or upload your medical notes, prescriptions, or daily records 📄 (Optional)", type=["png", "jpg", "jpeg", "pdf", "txt"])

    if st.button("Share with Care Team"):
        if user_input.strip() or uploaded_file is not None:
            st.session_state.wants_schedule = False
            st.session_state.calendar_synced = False
            st.session_state.calendar_platform = None
            st.session_state.calendar_events = {}
            st.session_state.all_created_events = [] 
            st.session_state.balloons_shown = False
            st.session_state.cycle_count = 1
            st.session_state.current_start_date = datetime.now()
            st.session_state.historical_schedules = []
            st.session_state.view_maintenance = False
            st.session_state.is_successful_conclusion = False
            
            # Reset tracking lists for Data Export
            st.session_state.initial_message = user_input.strip()
            st.session_state.weekly_messages = []
            st.session_state.severities = []
            st.session_state.consent_given = None
            st.session_state.data_exported = False
            
            for k in ["a6_res", "a8_res", "a10_res", "a11_res", "a12_res", "halt_msg"]: st.session_state[k] = None
            st.session_state.task_feedback = {}; st.session_state.plan_version = 1 
            
            with st.spinner("Reviewing your experience and documents..."):
                extracted_text = ""
                base64_image = None
                image_type = None

                if uploaded_file is not None:
                    if uploaded_file.type == "text/plain":
                        extracted_text = uploaded_file.read().decode("utf-8")
                    elif uploaded_file.type == "application/pdf":
                        pdf_reader = PyPDF2.PdfReader(uploaded_file)
                        for pdf_page in pdf_reader.pages:
                            extracted_text += pdf_page.extract_text() + "\n"
                    elif uploaded_file.type in ["image/png", "image/jpeg", "image/jpg"]:
                        base64_image = base64.b64encode(uploaded_file.read()).decode('utf-8')
                        image_type = uploaded_file.type

                # --- AGENT 1: CLINICAL INTAKE ---
                if base64_image:
                    a1_messages = [
                        {"role": "system", "content": "You are Agent 1. Extract symptoms from both the text and the image provided."},
                        {"role": "user", "content": [
                            {"type": "text", "text": f"User Input: {user_input}\n\nAnalyze the attached medical document image as well."},
                            {"type": "image_url", "image_url": {"url": f"data:{image_type};base64,{base64_image}"}}
                        ]}
                    ]
                    a1_raw = client.beta.chat.completions.parse(model="gpt-4o-mini", messages=a1_messages, response_format=ClinicalIntakeSchema)
                    a1 = a1_raw.choices[0].message.parsed
                    st.session_state.a1_res = a1
                else:
                    combined_input = user_input
                    if extracted_text: combined_input += f"\n\n--- Attached Document Content ---\n{extracted_text}"
                    a1 = run_agent(ClinicalIntakeSchema, "You are Agent 1. Extract symptoms.", combined_input)
                    st.session_state.a1_res = a1
                
                if a1.is_information_complete:
                    st.session_state.initial_severity = a1.severity_scale if a1.severity_scale is not None else 5
                    st.session_state.severities.append(st.session_state.initial_severity)
                    p1 = a1.model_dump_json()
                    
                    # --- AGENT 2: TRIAGE CLASSIFIER ---
                    a2 = run_agent(TriageClassification, "You are Agent 2. Route the JSON.", p1)
                    
                    if a2.routing_decision != "ROUTE_TO_INTAKE_LOOP":
                        # --- AGENT 3: RAG RETRIEVER ---
                        a3 = run_agent(RawRAGContextSchema, f"You are Agent 3. Fetch literature for {a2.routing_decision}.", p1)
                        
                        # --- AGENT 4: TRIAGE SYNTHESIZER ---
                        a4 = run_agent(TriageSynthesisSchema, "You are Agent 4. Synthesize data.", f"SYMPTOMS:\n{p1}\n\nRAG:\n{a3.retrieved_literature}")
                        st.session_state.a4_res = a4
                        st.session_state.possible_symptoms = ", ".join(a4.potential_conditions)
                        
                        # --- AGENT 5: PATIENT COMMUNICATOR ---
                        st.session_state.a5_res = run_agent(PatientCommunicationSchema, "You are Agent 5. Translate clinical data.", f"SYMPTOMS:\n{p1}\n\nSYNTHESIS:\n{a4.model_dump_json()}")
                        st.session_state.pipeline_done = True
                    else:
                        st.session_state.halt_msg = "Please provide a bit more detail regarding your timeline or severity."
                else:
                    st.session_state.halt_msg = a1.missing_fields_rationale
        else:
            st.error("Please provide some details or upload a file before sharing.")

    if st.session_state.halt_msg:
        st.markdown("---"); st.info(f"### 🍃 Gentle Guidance\n{st.session_state.halt_msg}")

    elif st.session_state.pipeline_done:
        st.markdown("---")
        
        focus_str = ', '.join(st.session_state.a1_res.primary_concerns) if st.session_state.a1_res.primary_concerns else 'None specified'
        dur_str = st.session_state.a1_res.symptom_duration or "Unknown"
        sev_str = f"{st.session_state.a1_res.severity_scale}/10" if st.session_state.a1_res.severity_scale else "Not rated"
        
        st.markdown(f"""
        <div style="background-color: #EBF8FF; padding: 25px; border-radius: 15px; margin-bottom: 25px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
            <h3 style="color: #2B6CB0; margin-top: 0;">📊 Your Results</h3>
            <p style="color: #2D3748; font-size: 16px;"><strong>Primary Focus:</strong> {focus_str}</p>
            <div style="display: flex; gap: 40px; margin-bottom: 20px;">
                <div><span style="color: #4A5568; font-size: 14px;">Duration</span><br><strong style="font-size: 22px; color: #2B6CB0;">{dur_str}</strong></div>
                <div><span style="color: #4A5568; font-size: 14px;">Initial Distress Level</span><br><strong style="font-size: 22px; color: #2B6CB0;">{sev_str}</strong></div>
            </div>
            <h4 style="color: #2B6CB0; margin-bottom: 5px;">🩹 Physical Signs Noted</h4>
            <ul style="color: #2D3748; margin-top: 0;">{format_list(st.session_state.a1_res.physical_indicators)}</ul>
            <h4 style="color: #2B6CB0; margin-bottom: 5px; margin-top: 15px;">🧠 Emotional & Mental Signs Noted</h4>
            <ul style="color: #2D3748; margin-top: 0;">{format_list(st.session_state.a1_res.emotional_indicators)}</ul>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div style="background-color: #E6FFFA; padding: 25px; border-radius: 15px; margin-bottom: 25px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
            <h3 style="color: #2C7A7B; margin-top: 0;">📋 Result Summary</h3>
            <p style="color: #2D3748; font-size: 16px;">{st.session_state.a4_res.underlying_mechanisms}</p>
            <h4 style="color: #2C7A7B; margin-bottom: 5px;">Potential Conditions Evaluated:</h4>
            <ul style="color: #2D3748; margin-top: 0;">{format_list(st.session_state.a4_res.potential_conditions)}</ul>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div style="background-color: #FFF5F5; padding: 25px; border-radius: 15px; margin-bottom: 25px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
            <h3 style="color: #C53030; margin-top: 0;">💌 A Message from Our Care Team</h3>
            <p style="color: #2D3748; font-size: 16px;">{st.session_state.a5_res.empathetic_summary}</p>
            <h4 style="color: #C53030; margin-bottom: 5px; margin-top: 15px;">Understanding Your Experience:</h4>
            <p style="color: #2D3748; margin-top: 0;">{st.session_state.a5_res.understanding_the_why}</p>
        </div>
        """, unsafe_allow_html=True)
        
        if not st.session_state.wants_schedule:
            st.markdown("""
            <div style="background-color: #F7FAFC; padding: 20px; border-radius: 15px; margin-bottom: 15px; border: 1px solid #E2E8F0;">
                <h3 style="color: #2D3748; margin-top: 0; margin-bottom: 5px;">📅 Personalize Your Care</h3>
                <p style="color: #4A5568; margin-top: 0;">Would you like us to create a personalized 7-day schedule to help you implement these recommendations?</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Yes, please create my 7-day schedule"):
                st.session_state.wants_schedule = True; st.rerun()
                
        if st.session_state.wants_schedule:
            if st.session_state.a6_res is None:
                # --- AGENT 6: MICRO-PLANNER ---
                with st.spinner(f"Building your custom 7-day schedule (Week {st.session_state.cycle_count})..."):
                    today_str = st.session_state.current_start_date.strftime("%A, %B %d, %Y")
                    agent_6_prompt = "You are Agent 6. Decompose steps using exact calendar dates. You MUST create EXACTLY 7 tasks (1 per day for 7 consecutive days)."
                    st.session_state.a6_res = run_agent(ActionPlanSchema, agent_6_prompt, f"START DATE: {today_str}\n\nCONTEXT:\n{st.session_state.a5_res.model_dump_json()}")
                    
                    # Automated Background Synchronization for Weeks 2+
                    if st.session_state.calendar_synced and st.session_state.calendar_platform:
                        st.session_state.calendar_events = {}
                        for task in st.session_state.a6_res.weekly_schedule:
                            evt_id = None
                            if "Google" in st.session_state.calendar_platform: 
                                evt_id = production_create_calendar_event(st.session_state.user_email, task)
                            elif "Outlook" in st.session_state.calendar_platform: 
                                evt_id = production_create_outlook_event(st.session_state.user_email, task)
                            if evt_id:
                                st.session_state.calendar_events[task.exact_date] = evt_id
                                st.session_state.all_created_events.append((evt_id, st.session_state.calendar_platform))
                    
            with st.container(border=True):
                st.markdown(f"<h3 style='color: #D69E2E; margin-top: 0; margin-bottom: 0;'>📅 Your Interactive Plan (Week {st.session_state.cycle_count})</h3>", unsafe_allow_html=True)
                st.write("Track your progress and easily sync the tasks with your favorite calendar below.")
                
                if not st.session_state.calendar_synced:
                    st.markdown("##### 🔗 Connect to your preferred calendar")
                    selected_platform = st.radio("Select Provider:", ["Google Calendar", "Microsoft Outlook / Teams"], horizontal=True)
                    
                    c1, c2 = st.columns([2, 1])
                    email_input = c1.text_input("Account Email:", value=st.session_state.user_email)
                    c2.markdown("<div style='padding-top: 28px;'></div>", unsafe_allow_html=True)
                    
                    if c2.button("📅 Sync Schedule"):
                        if email_input.strip() and "@" in email_input:
                            st.session_state.user_email = email_input.strip()
                            st.session_state.calendar_platform = selected_platform
                            
                            with st.spinner(f"Connecting to {selected_platform}..."):
                                for task in st.session_state.a6_res.weekly_schedule:
                                    evt_id = None
                                    if "Google" in selected_platform: 
                                        evt_id = production_create_calendar_event(st.session_state.user_email, task)
                                    elif "Outlook" in selected_platform: 
                                        evt_id = production_create_outlook_event(st.session_state.user_email, task)
                                    if evt_id:
                                        st.session_state.calendar_events[task.exact_date] = evt_id
                                        st.session_state.all_created_events.append((evt_id, selected_platform))
                            st.session_state.calendar_synced = True
                            st.toast("✅ Successfully synced your schedule!", icon="🎉")
                            st.rerun()
                        else: st.error("Please enter a valid email address.")
                else:
                    platform_icon = "🟦" if "Outlook" in st.session_state.calendar_platform else "🟩"
                    st.success(f"🔒 {platform_icon} Active Sync Connected to: **{st.session_state.user_email}** ({st.session_state.calendar_platform}). Tasks map automatically.")

                needs_adjustment = False
                all_completed = True
                options = ["Pending", "✅ Completed", "⏸️ Missed - Need to shift", "🏔️ Too Hard - Need an easier option"]
                lock_next = False
                
                for idx, task in enumerate(st.session_state.a6_res.weekly_schedule):
                    current_status = st.session_state.task_feedback.get(task.exact_date, "Pending")
                    c1, c2 = st.columns([3, 1])
                    c1.markdown(f"**{task.exact_date}:** {task.action_item}")
                    
                    status = c2.selectbox("Status:", options, index=options.index(current_status), key=f"task_{st.session_state.plan_version}_{idx}", disabled=lock_next)
                    st.session_state.task_feedback[task.exact_date] = status
                    
                    if status == "Pending": lock_next = True
                    if "Missed" in status or "Too Hard" in status: needs_adjustment = True
                    if status != "✅ Completed": all_completed = False
                    st.markdown("<hr class='day-divider'>", unsafe_allow_html=True)

                if needs_adjustment:
                    st.warning("It looks like the current plan might not fit your week perfectly right now. That is completely okay.")
                    if st.button("Recalibrate My Plan"):
                        # --- AGENT 7: DYNAMIC RESCHEDULER ---
                        with st.spinner("Recalibrating..."):
                            agent7_prompt = "You are Agent 7. Output a FULL 7-day schedule (EXACTLY 7 tasks). Keep 'Completed'/'Pending' identical. Make 'Too Hard'/'Missed' easier. Preserve exact calendar dates."
                            adjusted_plan = run_agent(AdjustedPlanSchema, agent7_prompt, f"PLAN:\n{st.session_state.a6_res.model_dump_json()}\n\nFEEDBACK:\n{json.dumps(st.session_state.task_feedback)}")
                            st.session_state.a6_res.weekly_schedule = adjusted_plan.weekly_schedule
                            
                            if st.session_state.calendar_synced:
                                for task in adjusted_plan.weekly_schedule:
                                    if "Missed" in st.session_state.task_feedback.get(task.exact_date, "") or "Too Hard" in st.session_state.task_feedback.get(task.exact_date, ""):
                                        evt_id = st.session_state.calendar_events.get(task.exact_date)
                                        if evt_id:
                                            if "Google" in st.session_state.calendar_platform: production_update_calendar_event(evt_id, st.session_state.user_email, task)
                                            elif "Outlook" in st.session_state.calendar_platform: production_update_outlook_event(evt_id, st.session_state.user_email, task)
                            
                            for day, status in st.session_state.task_feedback.items():
                                if "Missed" in status or "Too Hard" in status: st.session_state.task_feedback[day] = "Pending"
                            st.session_state.plan_version += 1; st.rerun()
                            
            if all_completed and len(st.session_state.a6_res.weekly_schedule) > 0:
                # ==========================================
                # 🔄 AGENT 12: WEEKLY CHECK-IN NLP
                # ==========================================
                if not st.session_state.get('view_maintenance'):
                    st.markdown("---")
                    st.markdown(f"### 🔄 Weekly Check-In (Week {st.session_state.cycle_count})")
                    st.write("You have successfully completed all your tasks for this week's cycle! Let's take a moment to evaluate your progress.")
                    
                    if st.session_state.a12_res is None:
                        check_in_input = st.text_area("How have you been feeling after completing this week's plan? Let us know about any changes in your physical or mental symptoms.", height=120, placeholder="e.g., I'm feeling slightly better, but my tension headaches are still bothering me occasionally...")
                        if st.button("Submit Reflection"):
                            if check_in_input.strip():
                                with st.spinner("Analyzing your progress..."):
                                    a12_prompt = "You are Agent 12, a clinical sentiment analyzer. Read the user's weekly check-in text carefully and estimate their current distress or symptom severity on a strict scale of 0 to 10 (where 10 is unbearable)."
                                    st.session_state.a12_res = run_agent(CheckInAnalysisSchema, a12_prompt, check_in_input)
                                    
                                    st.session_state.weekly_messages.append(check_in_input)
                                    st.session_state.severities.append(st.session_state.a12_res.estimated_severity)
                                    
                                st.rerun()
                            else:
                                st.error("Please share a brief update on how you are feeling before submitting.")
                    
                    else:
                        sev = st.session_state.a12_res.estimated_severity
                        init_sev = st.session_state.initial_severity
                        
                        if sev < 4:
                            st.success("Incredible work! Based on your reflection, your symptoms have significantly improved. You can now safely conclude your active planning cycles.")
                            st.session_state.is_successful_conclusion = True
                            
                            if len(st.session_state.historical_schedules) < st.session_state.cycle_count:
                                st.session_state.historical_schedules.append({"week": st.session_state.cycle_count, "plan": st.session_state.a6_res.model_dump()})
                            
                            if st.button("✅ View Next Steps & Export Record"):
                                st.session_state.view_maintenance = True
                                st.rerun()
                                
                        elif st.session_state.cycle_count >= 4:
                            st.error("You have completed the maximum 4-week program. Since your severity remains elevated, it is highly recommended that you consult a doctor or a medical professional for dedicated assistance.")
                            st.session_state.is_successful_conclusion = False
                            
                            if len(st.session_state.historical_schedules) < st.session_state.cycle_count:
                                st.session_state.historical_schedules.append({"week": st.session_state.cycle_count, "plan": st.session_state.a6_res.model_dump()})
                            
                            if st.button("✅ View Next Steps & Export Record"):
                                st.session_state.view_maintenance = True
                                st.rerun()
                            
                        else:
                            if sev < init_sev:
                                st.info("There is a noticeable improvement in your condition from your initial assessment! However, you are still encouraged to continue with the plan until your condition fully stabilizes.")
                            else:
                                st.warning("We are concerned to see that your condition has not improved, or has worsened, compared to your initial assessment. You are strongly encouraged to continue with the weekly plan. Meanwhile, if you feel no improvements, please consult your doctor or a medical professional for assistance.")
                            
                            st.session_state.is_successful_conclusion = False
                            
                            # Forced Loop Continuation
                            if st.button("🔄 Generate Next 7-Day Plan"):
                                if len(st.session_state.historical_schedules) < st.session_state.cycle_count:
                                    st.session_state.historical_schedules.append({"week": st.session_state.cycle_count, "plan": st.session_state.a6_res.model_dump()})
                                st.session_state.cycle_count += 1
                                st.session_state.a6_res = None
                                st.session_state.a12_res = None
                                st.session_state.task_feedback = {}
                                st.session_state.plan_version += 1
                                st.session_state.current_start_date += timedelta(days=7)
                                st.rerun()

                # Render Final Stages ONLY if concluded/failed out
                if st.session_state.get('view_maintenance'):
                    if st.session_state.a8_res is None:
                        # --- AGENT 8: MAINTENANCE COACH ---
                        with st.spinner("Preparing your final recommendations..."):
                            if st.session_state.is_successful_conclusion:
                                a8_prompt = "You are Agent 8. Provide maintenance guidance for a patient who has successfully completed their recovery plan."
                            else:
                                a8_prompt = "You are Agent 8. The patient has NOT improved after 4 weeks and requires medical attention. Provide serious next steps focusing on seeking professional medical or psychological help immediately. Use the 'congratulations_message' field to output a serious warning header (e.g., 'Medical Consultation Recommended'). Do NOT congratulate them."
                            
                            st.session_state.a8_res = run_agent(MaintenancePlanSchema, a8_prompt, st.session_state.a5_res.model_dump_json())
                            
                            # Global Calendar Wipe - Cleans all tracked weeks of generated events
                            if st.session_state.calendar_synced:
                                for evt_id, plat in st.session_state.all_created_events:
                                    if "Google" in plat: production_delete_calendar_event(evt_id)
                                    elif "Outlook" in plat: production_delete_outlook_event(evt_id)
                                st.toast("All tracked tasks from your Calendar have been removed.", icon="✨")
                    
                    if st.session_state.is_successful_conclusion:
                        if not st.session_state.balloons_shown:
                            st.balloons()
                            st.session_state.balloons_shown = True

                        st.markdown(f"""
                        <div style="background-color: #FAF5FF; padding: 25px; border-radius: 15px; margin-top: 25px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                            <h3 style="color: #6B46C1; margin-top: 0;">🎉 {st.session_state.a8_res.congratulations_message}</h3>
                            <h4 style="color: #6B46C1; margin-bottom: 5px;">🌟 Keeping the Momentum Going:</h4>
                            <ul style="color: #2D3748; margin-top: 0; margin-bottom: 0;">{format_list(st.session_state.a8_res.long_term_steps)}</ul>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                        <div style="background-color: #FFF5F5; padding: 25px; border-radius: 15px; margin-top: 25px; border: 1px solid #FC8181; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                            <h3 style="color: #C53030; margin-top: 0;">⚠️ {st.session_state.a8_res.congratulations_message}</h3>
                            <h4 style="color: #C53030; margin-bottom: 5px;">Recommended Medical Steps:</h4>
                            <ul style="color: #2D3748; margin-top: 0; margin-bottom: 0;">{format_list(st.session_state.a8_res.long_term_steps)}</ul>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    # ==========================================
                    # 🎨 AGENT 10: PROFESSIONAL EMAIL CRAFTER 
                    # ==========================================
                    st.markdown("---")
                    st.markdown("### 📥 Export Your Health Record")
                    st.write("Would you like a professional summary of your journey sent to your email? This is highly useful for keeping personal records or showing to your doctor during future medical appointments.")
                    
                    e_col1, e_col2, e_col3 = st.columns([1.5, 1.5, 1])
                    with e_col1:
                        patient_name = st.text_input("Your Full Name:", value=st.session_state.user_name, placeholder="e.g., Jane Doe")
                    with e_col2:
                        target_email = st.text_input("Send to Email:", value=st.session_state.user_email, placeholder="name@example.com")
                    
                    email_provider = st.selectbox("Select Email Provider:", ["Gmail", "Outlook / Teams", "Other Webmail"])

                    if st.button("📤 Draft & Send Summary"):
                        if target_email and patient_name:
                            st.session_state.user_name = patient_name
                            st.session_state.user_email = target_email
                            
                            with st.spinner("Crafting and sending your professional medical summary..."):
                                a10_payload = f"SYMPTOMS:\n{st.session_state.a1_res.model_dump_json()}\n\nSYNTHESIS:\n{st.session_state.a4_res.model_dump_json()}\n\nHISTORICAL COMPLETED PLANS (ALL WEEKS):\n{json.dumps(st.session_state.historical_schedules)}"
                                
                                if st.session_state.is_successful_conclusion:
                                    agent_10_prompt = f"You are Agent 10, the automated scribe for the 'Aura Wellbeing Team'. Draft a highly professional email to the patient ({patient_name}) summarizing their symptoms, expected conditions, and an HTML table containing ALL completed tasks from ALL tracked weeks. Instead of 'Success metrics', provide 'Recommended next steps' and explicitly include the exact phrase 'You have accomplished all your goals, well done!'. End the email warmly from the 'Aura Wellbeing Team'. DO NOT use any bracketed placeholders like [Your Name] or [Date]."
                                else:
                                    agent_10_prompt = f"You are Agent 10, the automated scribe for the 'Aura Wellbeing Team'. Draft a highly professional email to the patient ({patient_name}) summarizing their symptoms, expected conditions, and an HTML table containing ALL completed tasks from ALL tracked weeks. The patient did NOT improve after completing the schedule. Instead of 'Success metrics', provide 'Recommended next steps' and explicitly include the exact phrase 'Please share this comprehensive record with a medical professional for further diagnosis.' End the email warmly but professionally. DO NOT use bracketed placeholders like [Your Name] or [Date]. Do NOT congratulate them."
                                
                                st.session_state.a10_res = run_agent(EmailDraftSchema, agent_10_prompt, a10_payload)
                                
                                if email_provider == "Gmail": send_real_gmail(target_email, st.session_state.a10_res)
                                elif email_provider == "Outlook / Teams": send_real_outlook_email(target_email, st.session_state.a10_res)
                                    
                                st.success(f"✅ Securely sent via {email_provider} to {target_email}!")
                        else: st.error("Please enter your name and an email address first.")
                                
                    if st.session_state.a10_res:
                        with st.expander("📧 Click here to view the Email Preview", expanded=False):
                            clean_preview_html = st.session_state.a10_res.html_body.replace("```html", "").replace("```", "").strip()
                            st.markdown(f"""
                            <div class="email-container" style="background-color: #FFFFFF; padding: 25px; border-radius: 10px; border: 1px solid #CBD5E0; color: #2D3748; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                                <p style="margin-top: 0; color: #4A5568;"><strong>Subject:</strong> {st.session_state.a10_res.subject_line}</p>
                                <hr style="border: 0; border-top: 1px solid #E2E8F0; margin: 15px 0;">
                                {clean_preview_html}
                            </div>
                            """, unsafe_allow_html=True)
                    
                    # ==========================================
                    # 📚 AGENT 11: NEWS COLLATER (AI CURATED)
                    # ==========================================
                    st.markdown("---")
                    st.markdown("### 📰 Curated Light Reading")
                    st.write("Looking for some light reading? We have pulled a few highly credible articles specifically tailored to what you are experiencing today.")
                    
                    if st.button("Fetch Reading Materials"):
                        with st.spinner("Curating articles from our trusted medical database..."):
                            a11_payload = f"DATABASE: {json.dumps(CURATED_HEALTH_DATABASE)}\n\nUSER CONDITIONS: {st.session_state.a4_res.potential_conditions}\nUSER SYMPTOMS: {st.session_state.a1_res.primary_concerns}"
                            a11_prompt = "You are Agent 11, a Health News Collater. Read the USER CONDITIONS and SYMPTOMS. Then, select EXACTLY 6 articles from the provided JSON DATABASE that best match the user's situation. For each, write a custom 'brief_summary' explaining why it helps them. You MUST use the exact 'url' and 'image' links provided in the database."
                            st.session_state.a11_res = run_agent(NewsCollaterSchema, a11_prompt, a11_payload)
                    
                    if st.session_state.a11_res:
                        st.info(st.session_state.a11_res.encouraging_intro)
                        articles = st.session_state.a11_res.curated_articles
                        
                        for row_idx in range(0, 6, 3):
                            cols = st.columns(3)
                            for col_idx in range(3):
                                list_idx = row_idx + col_idx
                                if list_idx < len(articles):
                                    article = articles[list_idx]
                                    
                                    with cols[col_idx]:
                                        st.markdown(f"""
                                        <div style="background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 15px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                                            <img src="{article.image_url}" onerror="this.onerror=null; this.src='https://placehold.co/400x200/EBF8FF/2B6CB0?text=Health+Article';" style="width: 100%; height: 140px; object-fit: cover; border-radius: 8px; margin-bottom: 15px;">
                                            <h5 style='color: #2B6CB0; margin-top: 0px; margin-bottom: 5px; font-size: 16px; height: 45px; overflow: hidden;'>{article.headline}</h5>
                                            <p style='color: #4A5568; font-size: 13px; height: 60px; overflow: hidden; margin-bottom: 15px;'>{article.brief_summary}</p>
                                            <a href="{article.article_url}" target="_blank" style="display: block; text-align: center; background-color: #EBF8FF; color: #2B6CB0; padding: 8px; border-radius: 5px; text-decoration: none; font-weight: bold; border: 1px solid #BEE3F8;">Read Article ↗</a>
                                        </div>
                                        """, unsafe_allow_html=True)
                                        
                    # ==========================================
                    # 📝 AGENT 12: RESEARCH DATA CURATOR
                    # ==========================================
                    st.markdown("---")
                    st.markdown("### 📊 Research Data Contribution")
                    st.write("Would you be open to anonymously sharing your symptom progression data for research purposes? This helps us improve our algorithm's accuracy for future users facing similar conditions.")

                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("✅ Yes, I consent to data transfer"):
                            st.session_state.consent_given = True
                            st.rerun()
                    with c2:
                        if st.button("❌ No, I prefer to keep it private"):
                            st.session_state.consent_given = False
                            st.rerun()

                    if st.session_state.consent_given is False:
                        st.info("We appreciate your option of not revealing your data.")
                    elif st.session_state.consent_given is True:
                        if not st.session_state.get("data_exported"):
                            with st.spinner("Exporting your data to the research database..."):
                                
                                padded_messages = st.session_state.weekly_messages + ["NA"] * (4 - len(st.session_state.weekly_messages))
                                padded_severities = st.session_state.severities + ["NA"] * (5 - len(st.session_state.severities))
                                
                                data = {
                                    "Name": st.session_state.user_name if st.session_state.user_name else "Anonymous",
                                    "Email": st.session_state.user_email if st.session_state.user_email else "NA",
                                    "Initial Message": st.session_state.initial_message,
                                    "Possible Symptoms": st.session_state.possible_symptoms,
                                    "Week 1 Message": padded_messages[0],
                                    "Week 2 Message": padded_messages[1],
                                    "Week 3 Message": padded_messages[2],
                                    "Week 4 Message": padded_messages[3],
                                    "Initial Severity": padded_severities[0],
                                    "Week 1 Severity": padded_severities[1],
                                    "Week 2 Severity": padded_severities[2],
                                    "Week 3 Severity": padded_severities[3],
                                    "Week 4 Severity": padded_severities[4]
                                }
                                
                                df = pd.DataFrame([data])
                                file_name = "research_database.xlsx"
                                try:
                                    if os.path.exists(file_name):
                                        existing_df = pd.read_excel(file_name)
                                        combined_df = pd.concat([existing_df, df], ignore_index=True)
                                        combined_df.to_excel(file_name, index=False)
                                    else:
                                        df.to_excel(file_name, index=False)
                                    st.session_state.data_exported = True
                                except Exception as e:
                                    st.error(f"Error exporting data: {e}")
                        
                        if st.session_state.get("data_exported"):
                            st.success("✅ Your data has been securely transferred. Thank you for contributing to medical research!")
                            
                            if os.path.exists("research_database.xlsx"):
                                with open("research_database.xlsx", "rb") as f:
                                    st.download_button(
                                        label="📥 Download Research Database (.xlsx)",
                                        data=f,
                                        file_name="research_database.xlsx",
                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                    )

# ==========================================
# PAGE 2: NEWSFEED (Static non-AI Portion)
# ==========================================
elif page == "Newsfeed":
    st.title("📰 Aura Library: All Articles")
    st.markdown("Browse our complete collection of verified health and wellbeing articles below. No matter what you are looking for, we have credible resources to support your journey.")
    
    search_query = st.text_input("Search", placeholder="🔍 Search articles by keyword (e.g., sleep, anxiety, back pain)...", label_visibility="collapsed").lower()
    st.markdown("---")
    
    filtered_db = [
        article for article in CURATED_HEALTH_DATABASE
        if search_query in article['topic'].lower() or search_query in article['description'].lower() or search_query in article['source'].lower()
    ]
    
    if not filtered_db:
        st.warning("No articles found matching your keywords. Try another search!")
    else:
        for row_idx in range(0, len(filtered_db), 3):
            cols = st.columns(3)
            for col_idx in range(3):
                list_idx = row_idx + col_idx
                if list_idx < len(filtered_db):
                    article = filtered_db[list_idx]
                    with cols[col_idx]:
                        st.markdown(f"""
                        <div style="background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 15px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                            <img src="{article['image']}" onerror="this.onerror=null; this.src='https://placehold.co/400x200/EBF8FF/2B6CB0?text=Health+Article';" style="width: 100%; height: 140px; object-fit: cover; border-radius: 8px; margin-bottom: 15px;">
                            <h5 style='color: #2B6CB0; margin-top: 0px; margin-bottom: 5px; font-size: 16px; height: 45px; overflow: hidden;'>{article['topic']}</h5>
                            <p style='color: #4A5568; font-size: 13px; height: 60px; overflow: hidden; margin-bottom: 15px;'>{article['description']}</p>
                            <a href="{article['url']}" target="_blank" style="display: block; text-align: center; background-color: #EBF8FF; color: #2B6CB0; padding: 8px; border-radius: 5px; text-decoration: none; font-weight: bold; border: 1px solid #BEE3F8;">Read Article ↗</a>
                        </div>
                        """, unsafe_allow_html=True)

# ==========================================
# PAGE 3: MY HEALTH INSIGHTS
# ==========================================
elif page == "My Health Insights":
    st.title("📈 My Health Insights")
    st.markdown("Explore your historical health trends and identified triggers over the past 6 months.")
    st.markdown("---")

    # 1. Line Chart: Average Sleep Duration
    st.markdown("### 💤 Your Average Sleep Duration Over The Months")
    sleep_df = pd.DataFrame({
        "Month": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
        "Sleep Duration (Hours)": [5.2, 5.5, 6.0, 6.2, 7.1, 7.5]
    })
    
    line = alt.Chart(sleep_df).mark_line(point=True, strokeWidth=3).encode(
        x=alt.X('Month', sort=["Jan", "Feb", "Mar", "Apr", "May", "Jun"], title="", axis=alt.Axis(labelAngle=0, grid=False, labelColor='black', labelFontWeight='bold', labelFontSize=13)),
        y=alt.Y('Sleep Duration (Hours)', title="Hours", scale=alt.Scale(domain=[0, 10]), axis=alt.Axis(grid=False, labelColor='black', labelFontWeight='bold', labelFontSize=13, titleColor='black', titleFontWeight='bold', titleFontSize=14))
    )
    # FORCE METRIC TO SOLID BOLD BLACK VIA PARAMETERS
    line_labels = line.mark_text(align='center', baseline='bottom', dy=-10, fontSize=13, fontWeight='bold', color='black').encode(
        text=alt.Text('Sleep Duration (Hours):Q', format='.1f')
    )
    sleep_chart = (line + line_labels).properties(height=350).configure_view(strokeWidth=0).configure(background='transparent')
    st.altair_chart(sleep_chart, width="stretch")

    st.markdown("<br>", unsafe_allow_html=True)

    # 2. Bar Chart with Gradient: Depression Levels
    st.markdown("### 🌧️ Your Depression Levels By Month")
    dep_df = pd.DataFrame({
        "Month": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
        "Depression Level": [8, 8, 7, 6, 4, 3]
    })
    
    bars = alt.Chart(dep_df).mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5).encode(
        x=alt.X('Month', sort=["Jan", "Feb", "Mar", "Apr", "May", "Jun"], title="", axis=alt.Axis(labelAngle=0, grid=False, labelColor='black', labelFontWeight='bold', labelFontSize=13)),
        y=alt.Y('Depression Level', title="Severity (0-10)", scale=alt.Scale(domain=[0, 10]), axis=alt.Axis(grid=False, labelColor='black', labelFontWeight='bold', labelFontSize=13, titleColor='black', titleFontWeight='bold', titleFontSize=14)),
        color=alt.Color('Depression Level', scale=alt.Scale(scheme='reds'), legend=None),
        tooltip=[alt.Tooltip('Month:N', title='Month'), alt.Tooltip('Depression Level:Q', title='Depression Level')]
    )
    
    # ISOLATED INDEPENDENT TEXT LAYER TO COMPLETELY BYPASS COLOR GRADIENT INHERITANCE
    bar_labels = alt.Chart(dep_df).mark_text(align='center', baseline='bottom', dy=-5, fontSize=13, fontWeight='bold', color='black').encode(
        x=alt.X('Month', sort=["Jan", "Feb", "Mar", "Apr", "May", "Jun"]),
        y=alt.Y('Depression Level'),
        text='Depression Level:Q'
    )
    
    bar_chart = (bars + bar_labels).properties(height=350).configure_view(strokeWidth=0).configure(background='transparent')
    st.altair_chart(bar_chart, width="stretch")

    st.markdown("<br>", unsafe_allow_html=True)

    # 3. Pie Chart: Factors Affecting Health
    st.markdown("### 🧩 Factors Affecting Your Health")
    factors_df = pd.DataFrame({
        "Factor": ["Work Stress", "Poor Diet", "Lack of Sleep", "Financial Worry", "Other"],
        "Impact (%)": [40.0, 20.0, 25.0, 10.0, 5.0]
    })
    
    pie_chart = alt.Chart(factors_df).mark_arc(innerRadius=50, outerRadius=120).encode(
        theta=alt.Theta(field="Impact (%)", type="quantitative"),
        color=alt.Color(field="Factor", type="nominal", scale=alt.Scale(scheme='set2'), legend=alt.Legend(orient='right', offset=-30, labelColor='black', labelFontWeight='bold', labelFontSize=14, titleColor='black', titleFontWeight='bold', titleFontSize=15, symbolSize=250)),
        tooltip=[alt.Tooltip('Factor:N'), alt.Tooltip('Impact (%):Q', format='.1f')]
    ).properties(height=350).configure_view(strokeWidth=0).configure(background='transparent')
    
    st.altair_chart(pie_chart, width="stretch")

# ==========================================
# PAGE 4: EMERGENCY CONTACTS
# ==========================================
elif page == "Emergency Contacts":
    st.title("🚨 Emergency Contacts & Support")
    st.markdown("""
    If you or someone you know is experiencing an immediate crisis or serious health threat, please contact the emergency responders without delay.

    ### 🇸🇬 Singapore Helplines
    * **Emergency Medical Services / Ambulance:** 995
    * **Police Urgent Response Line:** 999
    * **Samaritans of Singapore (SOS) Mental Health Line - 24/7:** 1-767
    * **Institute of Mental Health (IMH) Emergency Line:** 6389-2222
    * **National Care Lifeline Hotline:** 1800-202-6868

    ### 🌍 Global Support
    If you are utilizing this sanctuary framework outside Singapore borders, kindly lookup your regional localized protective responders or travel directly to the nearest hospital triage ward.
    """)