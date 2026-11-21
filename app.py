import streamlit as st
from google import genai
from google.genai import types
import json, os, re, time, io
from datetime import datetime, timedelta
from gtts import gTTS
import pandas as pd

# File reading libraries
import PyPDF2
import openpyxl

try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False

try:
    from streamlit_mic_recorder import mic_recorder
    HAS_MIC = True
except ImportError:
    HAS_MIC = False

# ==========================================
# 1. PREMIUM UI/UX & PAGE CONFIG
# ==========================================
st.set_page_config(page_title="Madam Shama AI Coach", page_icon="👩‍🏫", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background-color: #0b0f19; color: #e2e8f0; font-family: 'Inter', sans-serif; }
    .stChatMessage { border-radius: 20px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    .stChatMessage[data-testid="stChatMessageUser"] { background-color: #1e293b; color: #f8fafc !important; border-bottom-right-radius: 4px;}
    .stChatMessage[data-testid="stChatMessageAssistant"] { background-color: #0f172a; border-left: 4px solid #8b5cf6; color: #f8fafc !important; border-bottom-left-radius: 4px;}
    .stChatMessage p, .stChatMessage li, .stChatMessage span, .stChatMessage div { color: #f8fafc !important; font-size: 1.05rem; line-height: 1.6; }
    
    [data-testid="stSidebar"] { background-color: #0f172a; border-right: 1px solid #1e293b; }
    [data-testid="stSidebar"] * { color: #f8fafc !important; }
    [data-testid="stSidebar"] .stButton>button { color: #000000 !important; }
    
    /* Google Meet Style Interview Room */
    .meet-room { background-color: #202124; padding: 30px; border-radius: 20px; border: 1px solid #3c4043; margin-bottom: 20px; }
    .video-grid { display: flex; justify-content: center; gap: 20px; margin-bottom: 20px; }
    .video-card { background-color: #3c4043; width: 250px; height: 180px; border-radius: 15px; display: flex; flex-direction: column; align-items: center; justify-content: center; border: 2px solid #5f6368; }
    .video-card.active { border: 3px solid #8b5cf6; box-shadow: 0 0 20px rgba(139, 92, 246, 0.5); }
    .avatar { font-size: 60px; margin-bottom: 10px; }
    .name-tag { background-color: rgba(0,0,0,0.6); padding: 4px 12px; border-radius: 10px; font-size: 14px; }
    
    /* Skill Builder Project Card */
    .project-card { background-color: #1e293b; padding: 20px; border-radius: 15px; border-left: 5px solid #10b981; margin-bottom: 15px; }
    .project-title { color: #10b981 !important; font-size: 1.2rem; font-weight: bold; margin-bottom: 10px; }
    
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

st.title("👩‍🏫 Madam Shama: Your AI Coach")
st.caption("Warm, patient, and ready to guide you.")

# ==========================================
# 2. MEMORY & API
# ==========================================
PROFILE_FILE = "user_profile.json"
def save_memory(data):
    tmp = PROFILE_FILE + ".tmp"
    with open(tmp, "w") as f: json.dump(data, f)
    os.replace(tmp, PROFILE_FILE)

def load_memory():
    if not os.path.exists(PROFILE_FILE): return None
    try:
        with open(PROFILE_FILE) as f: return json.load(f)
    except: return None

try: api_key = st.secrets["GEMINI_API_KEY"]
except: api_key = st.sidebar.text_input("Enter Gemini API Key", type="password", value="")

@st.cache_resource
def get_client(key): return genai.Client(api_key=key) if key and key.strip() else None
client = get_client(api_key)
if not client:
    st.info("👈 Please enter your Gemini API key in the sidebar to begin.")
    st.stop()

FAST_MODEL = "gemini-2.5-flash"

COACH_PERSONA = """
You are "Madam Shama," a caring, patient, and deeply knowledgeable career and exam coach.
YOUR TONE: Warm, encouraging, never condescending. Use analogies. 
YOUR BOUNDARIES: Never give the answer to a live quiz directly. Guide them.
"""

def get_ai_response(prompt, json_mode=False):
    full_prompt = f"{COACH_PERSONA}\n\n---\n\n{prompt}"
    config = {"response_mime_type": "application/json"} if json_mode else {}
    try:
        response = client.models.generate_content(model=FAST_MODEL, contents=full_prompt, config=types.GenerateContentConfig(**config) if config else None)
        return response.text
    except Exception as e:
        return f"AI Error: {e}"

def play_voice(text, tld='co.uk'):
    clean = re.sub(r"[*#\[\]_>|`~]", "", text).strip()
    if not clean or len(clean) < 3: return None
    try:
        tts = gTTS(text=clean, lang='en', tld=tld)
        audio = io.BytesIO(); tts.write_to_fp(audio); audio.seek(0)
        return audio
    except: return None

def transcribe_audio(audio_bytes):
    try:
        response = client.models.generate_content(model=FAST_MODEL, contents=["Transcribe exactly. Return only text.", types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav")])
        return response.text.strip()
    except Exception as e:
        return None

def calculate_readiness(user_data):
    gaps = user_data.get("roadmap_data", {}).get("gaps", [])
    high_gaps = sum(1 for g in gaps if g.get("priority") == "High")
    gap_score = max(0, 40 - (high_gaps * 10))
    quiz_hist = user_data.get("quiz_scores", [])
    quiz_score = (sum(quiz_hist[-3:]) / len(quiz_hist[-3:]) / 100) * 30 if quiz_hist else 0
    int_hist = user_data.get("interview_scores", [])
    int_score = (sum(int_hist) / len(int_hist) / 10) * 30 if int_hist else 0
    skill_pts = user_data.get("skill_projects_completed", 0) * 5 
    total = min(100, max(0, round(gap_score + quiz_score + int_score + skill_pts)))
    return {"total": total, "breakdown": {"Knowledge": f"{round(gap_score)}/40", "Quizzes": f"{round(quiz_score)}/30", "Interviews": f"{round(int_score)}/30"}}

# ==========================================
# 3. STATE INIT
# ==========================================
if "messages" not in st.session_state:
    st.session_state.messages = []
    memory = load_memory()
    if memory:
        st.session_state.user_data = memory
        greeting = f"Welcome back! Let's continue your prep for **{memory.get('role', 'your goal')}**."
    else:
        st.session_state.user_data = {"step": "ask_role"}
        greeting = "Hello! I'm Madam Shama. Tell me: **what exam or job role are you preparing for?**"
    st.session_state.messages.append({"role": "assistant", "content": greeting, "is_new": True})

# ==========================================
# 4. SIDEBAR
# ==========================================
with st.sidebar:
    if st.button("🔄 Start New Conversation", use_container_width=True):
        if os.path.exists(PROFILE_FILE): os.remove(PROFILE_FILE)
        st.session_state.clear()
        st.rerun()
    st.divider()

    st.markdown("### 🎯 Readiness")
    if st.session_state.user_data.get("roadmap_data"):
        result = calculate_readiness(st.session_state.user_data)
        st.metric(label="Score", value=f"{result['total']}/100")
        st.progress(result['total'] / 100)
        st.caption(f"📚 {result['breakdown']['Knowledge']} | 🧠 {result['breakdown']['Quizzes']} | 🎤 {result['breakdown']['Interviews']}")
    else:
        st.info("Setup roadmap to see score.")

    st.divider()
    st.markdown("### 🎮 Modes")
    mode = st.radio("Select Mode:", ["💬 General Coach", "🎤 Voice Interview", "📝 Written Exam", "🧠 Rapid Quiz", "🛠️ Skill Builder"], key="practice_mode")
    
    tld = st.selectbox("Madam Shama's Accent", ["co.uk (British)", "com (American)", "com.au (Australian)"])
    voice_tld = tld.split(" ")[0]

# ==========================================
# 5. RENDER CHAT
# ==========================================
if mode not in ["🧠 Rapid Quiz", "🎤 Voice Interview"]:
    for i, msg in enumerate(st.session_state.messages):
        avatar = "👩‍🏫" if msg["role"] == "assistant" else "🧑"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and msg.get("is_new"):
                audio = play_voice(msg["content"], tld=voice_tld)
                if audio: st.audio(audio, format="audio/mp3", autoplay=True)
                st.session_state.messages[i]["is_new"] = False

# ==========================================
# 6. MODE SPECIFIC UI & INPUTS
# ==========================================
final_input = None

# --- RAPID QUIZ ---
if mode == "🧠 Rapid Quiz" and st.session_state.user_data.get("step") == "coach_mode":
    st.subheader("🧠 Rapid Fire Quiz")
    quiz_state = st.session_state.user_data.get("quiz_state", {})
    
    if not quiz_state.get("current_q"):
        if st.button("🚀 Start New Question", use_container_width=True):
            raw = get_ai_response(f"Generate 1 MCQ for {st.session_state.user_data['role']}. JSON: {{'question': '', 'options': ['A', 'B', 'C', 'D'], 'correct_answer': 'A', 'explanation': ''}}", json_mode=True)
            try:
                q = json.loads(raw)
                st.session_state.user_data["quiz_state"] = {"current_q": q["question"], "options": q["options"], "correct_answer": q["correct_answer"], "explanation": q["explanation"], "answered": False}
                st.rerun()
            except: st.error("Failed to generate quiz.")
    else:
        st.info(f"**Question:** {quiz_state['current_q']}")
        st.write("---")
        if not quiz_state.get("answered"):
            cols = st.columns(2)
            for idx, opt in enumerate(quiz_state["options"]):
                col = cols[idx % 2]
                if col.button(opt, use_container_width=True):
                    correct = quiz_state["correct_answer"]
                    if opt.strip().upper().startswith(correct.upper()):
                        st.success(f"✅ **Correct!** {quiz_state['explanation']}")
                        st.session_state.user_data["quiz_score"] = st.session_state.user_data.get("quiz_score", 0) + 1
                    else:
                        st.error(f"❌ **Not quite.** Answer was **{correct}**. {quiz_state['explanation']}")
                    if "quiz_scores" not in st.session_state.user_data: st.session_state.user_data["quiz_scores"] = []
                    st.session_state.user_data["quiz_scores"].append((st.session_state.user_data.get("quiz_score", 0) / 5) * 100)
                    st.session_state.user_data["quiz_state"]["answered"] = True
                    time.sleep(2)
                    st.session_state.user_data["quiz_state"]["current_q"] = None
                    st.rerun()

# --- GOOGLE MEET STYLE VOICE INTERVIEW ---
elif mode == "🎤 Voice Interview":
    st.markdown("""
    <div class="meet-room">
        <div class="video-grid">
            <div class="video-card active">
                <div class="avatar">🧑</div>
                <div class="name-tag">You (Candidate)</div>
            </div>
            <div class="video-card">
                <div class="avatar">👩‍🏫</div>
                <div class="name-tag">Madam Shama (Interviewer)</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if not st.session_state.user_data.get("interview_mode"):
        st.session_state.user_data["interview_mode"] = True
        st.session_state.user_data["interview_turn"] = 0
        ai_start = get_ai_response(f"Ask the first interview question for a {st.session_state.user_data['role']} role.")
        st.session_state.messages.append({"role": "assistant", "content": f"**[Interview Started]**\n\n{ai_start}", "is_new": True})
    
    for msg in st.session_state.messages[-2:]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and msg.get("is_new"):
                audio = play_voice(msg["content"], tld=voice_tld)
                if audio: st.audio(audio, format="audio/mp3", autoplay=True)
                msg["is_new"] = False

    if HAS_MIC:
        st.write("---")
        st.write("🎙️ **Speak your answer now...**")
        audio = mic_recorder(start_prompt="Click to Speak", stop_prompt="Click to Stop", just_once=True, key='recorder')
        if audio:
            with st.spinner("🎧 Transcribing instantly..."):
                transcribed = transcribe_audio(audio['bytes'])
                if transcribed: final_input = transcribed

# --- WRITTEN EXAM, GENERAL, SKILL BUILDER, FILE UPLOAD ---
else:
    uploaded_file = None
    if mode in ["📝 Written Exam", "💬 General Coach"]:
        uploaded_file = st.file_uploader("📂 Upload an Image, PDF, Excel, or PowerPoint", type=["jpg", "jpeg", "png", "pdf", "xlsx", "pptx"])
        if uploaded_file:
            file_size_mb = uploaded_file.size / (1024 * 1024)
            st.info(f"📄 **File Uploaded:** {uploaded_file.name} ({file_size_mb:.2f} MB)")
            if uploaded_file.type.startswith("image"):
                st.image(uploaded_file, caption="Your image", width=300)
            final_input = "ANALYZE_FILE"

    if not uploaded_file:
        user_input = st.chat_input("Type your message or answer...")
        if user_input: final_input = user_input

# ==========================================
# 7. AGENT LOGIC
# ==========================================
if final_input and final_input.strip():
    display_text = "📂 [Uploaded a file]" if final_input == "ANALYZE_FILE" else final_input
    st.session_state.messages.append({"role": "user", "content": display_text})
    
    step = st.session_state.user_data.get("step", "ask_role")
    ai_reply = ""

    with st.spinner("Madam Shama is analyzing..."):
        # Onboarding
        if step == "ask_role":
            st.session_state.user_data["role"] = final_input
            st.session_state.user_data["step"] = "ask_skills"
            save_memory(st.session_state.user_data)
            ai_reply = get_ai_response(f"User wants to prepare for: '{final_input}'. Acknowledge warmly. Ask about their current background/skills.")

        elif step == "ask_skills":
            st.session_state.user_data["skills"] = final_input
            st.session_state.user_data["step"] = "coach_mode"
            raw = get_ai_response(f"Target: {st.session_state.user_data['role']}. Skills: {final_input}. Create 4-week roadmap. Return ONLY JSON: {{'readiness_score': 50, 'summary': 'warm text', 'gaps': [{{'skill': '', 'why': '', 'priority': 'High'}}], 'roadmap': [{{'week': 1, 'focus': '', 'tasks': ['']}}]}}", json_mode=True)
            try:
                st.session_state.user_data["roadmap_data"] = json.loads(raw)
                save_memory(st.session_state.user_data)
                ai_reply = "I've built your **Roadmap** (see sidebar). Ready to practice?"
            except: ai_reply = "Could you repeat your skills?"

        # INTERVIEW
        elif step == "coach_mode" and mode == "🎤 Voice Interview":
            turn = st.session_state.user_data.get("interview_turn", 0)
            role = "HR Manager" if turn % 2 == 0 else "Senior Interviewer"
            ai_reply = get_ai_response(f"You are a {role}. Candidate answered: '{final_input}'. Score /10 using 'Score: X/10'. IF SCORE < 5, explain like a teacher. ELSE, ask next question.")
            st.session_state.user_data["interview_turn"] = turn + 1
            match = re.search(r'(\d+(?:\.\d+)?)\s*/\s*10', ai_reply)
            if match: 
                if "interview_scores" not in st.session_state.user_data: st.session_state.user_data["interview_scores"] = []
                st.session_state.user_data["interview_scores"].append(float(match.group(1)))
            save_memory(st.session_state.user_data)

        # SKILL BUILDER
        elif step == "coach_mode" and mode == "🛠️ Skill Builder":
            prompt = f"The user wants to learn: '{final_input}'. Provide a 3-step micro-project. Format EXACTLY: [TITLE] Project Name \n [STEP] Step 1 \n [STEP] Step 2 \n [STEP] Step 3 \n [RESOURCE] Link"
            raw = get_ai_response(prompt)
            formatted_html = '<div class="project-card"><div class="project-title">🛠️ Practical Project Assigned</div>'
            for line in raw.split('\n'):
                if line.startswith('[TITLE]'): formatted_html += f"<h4>{line.replace('[TITLE]', '').strip()}</h4>"
                elif line.startswith('[STEP]'): formatted_html += f"<p>☑️ {line.replace('[STEP]', '').strip()}</p>"
                elif line.startswith('[RESOURCE]'): formatted_html += f"<p style='color:#fbbf24;'>📚 <b>Resource:</b> {line.replace('[RESOURCE]', '').strip()}</p>"
            formatted_html += '</div>'
            st.markdown(formatted_html, unsafe_allow_html=True)
            ai_reply = "Complete it, then click below!"
            if st.button("✅ I Finished This Project!"):
                st.session_state.user_data["skill_projects_completed"] = st.session_state.user_data.get("skill_projects_completed", 0) + 1
                save_memory(st.session_state.user_data)
                ai_reply = "Fantastic work! You've earned +5 Readiness Points."
                st.rerun()

        # FILE ANALYSIS
        elif final_input == "ANALYZE_FILE" and uploaded_file:
            file_bytes = uploaded_file.read()
            extracted_text = ""
            
            if uploaded_file.type.startswith("image"):
                prompt = f"Analyze this image. If it is a DSA/Coding question, solve it step-by-step. If it is an answer sheet, grade it /10 and find every error."
                try:
                    response = client.models.generate_content(model=FAST_MODEL, contents=[prompt, types.Part.from_bytes(data=file_bytes, mime_type="image/jpeg")])
                    ai_reply = response.text
                except Exception as e: ai_reply = f"Error reading image: {e}"
            else:
                try:
                    if uploaded_file.type == "application/pdf":
                        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
                        for page in reader.pages:
                            extracted_text += page.extract_text() + "\n"
                    elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
                        df = pd.read_excel(io.BytesIO(file_bytes))
                        extracted_text = df.to_string()
                    
                    prompt = f"Analyze this document for a {st.session_state.user_data['role']} student. Read the text and provide feedback:\n\n{extracted_text[:4000]}"
                    ai_reply = get_ai_response(prompt)
                except Exception as e:
                    ai_reply = f"Could not read the file. Try a screenshot instead. Error: {e}"
            
        else:
            ai_reply = get_ai_response(f"User preparing for {st.session_state.user_data['role']}. They say: '{final_input}'. Respond warmly.")

    if ai_reply:
        st.session_state.messages.append({"role": "assistant", "content": ai_reply, "is_new": True})
    st.rerun()
