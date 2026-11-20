import streamlit as st
from google import genai
from google.genai import types
import json, os, re, time, io
from datetime import datetime, timedelta
from gtts import gTTS
import pandas as pd

try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False

# ==========================================
# 1. PREMIUM UI/UX & PAGE CONFIG
# ==========================================
st.set_page_config(page_title="Maya AI Coach", page_icon="🧑‍🏫", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    /* Global App Styling */
    .stApp { background-color: #0b0f19; color: #e2e8f0; font-family: 'Inter', sans-serif; }
    
    /* Chat Bubbles */
    .stChatMessage { border-radius: 20px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    .stChatMessage[data-testid="stChatMessageUser"] { background-color: #1e293b; color: #f8fafc !important; border-bottom-right-radius: 4px;}
    .stChatMessage[data-testid="stChatMessageAssistant"] { background-color: #0f172a; border-left: 4px solid #8b5cf6; color: #f8fafc !important; border-bottom-left-radius: 4px;}
    
    /* Chat Text Visibility Fix */
    .stChatMessage p, .stChatMessage li, .stChatMessage span, .stChatMessage div { color: #f8fafc !important; font-size: 1.05rem; line-height: 1.6; }
    
    /* Typing Box */
    .stChatInput textarea { color: #000000 !important; background-color: #ffffff !important; border-radius: 15px; }
    
    /* Sidebar Styling & Font Visibility Fix */
    [data-testid="stSidebar"] { background-color: #0f172a; border-right: 1px solid #1e293b; }
    [data-testid="stSidebar"] * { color: #f8fafc !important; }
    [data-testid="stSidebar"] .stButton>button { color: #000000 !important; }
    
    /* Pomodoro Timer */
    .timer-box { 
        background: linear-gradient(135deg, #1e1b4b, #312e81); 
        padding: 20px; 
        border-radius: 15px; 
        text-align: center; 
        border: 2px solid #8b5cf6;
        box-shadow: 0 0 20px rgba(139, 92, 246, 0.3);
    }
    .timer-text { 
        font-size: 48px; 
        font-weight: 800; 
        color: #a78bfa !important; 
        font-family: monospace;
        letter-spacing: 2px;
    }
    
    /* Hide default Streamlit elements */
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    
    /* Custom Buttons (Main page) */
    .stButton>button { border-radius: 10px; font-weight: 600; transition: all 0.3s; }
    .stButton>button:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(139, 92, 246, 0.4); }
    </style>
""", unsafe_allow_html=True)

st.title("🧑‍🏫 Maya: Your AI Coach")
st.caption("Warm, patient, and ready to guide you through any exam or interview.")

# ==========================================
# 2. MEMORY
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

# ==========================================
# 3. API & HELPERS
# ==========================================
try: api_key = st.secrets["GEMINI_API_KEY"]
except: api_key = st.sidebar.text_input("Enter Gemini API Key", type="password", value="")

@st.cache_resource
def get_client(key): return genai.Client(api_key=key) if key and key.strip() else None
client = get_client(api_key)
if not client:
    st.info("👈 Please enter your Gemini API key in the sidebar to begin.")
    st.stop()

COACH_PERSONA = """
You are "Maya," a caring, patient, and deeply knowledgeable career and exam coach.
YOUR TONE: Warm, encouraging, never condescending. Use analogies. 
YOUR ROLE: You can coach for ANY exam, job role, or career path on Earth. Do NOT assume the category. 
If the user gives you MULTIPLE goals, acknowledge them but ask to focus on ONE first.
YOUR BOUNDARIES: Never give the answer to a live quiz directly. Guide them. Never shame the user.
"""

def get_ai_response(prompt, json_mode=False):
    full_prompt = f"{COACH_PERSONA}\n\n---\n\n{prompt}"
    model_list = ["gemini-3.5-flash", "gemini-2.5-flash", "gemini-3.5-flash-lite"]
    config = {"response_mime_type": "application/json"} if json_mode else {}
    for m in model_list:
        try:
            response = client.models.generate_content(model=m, contents=full_prompt, config=types.GenerateContentConfig(**config) if config else None)
            return response.text
        except Exception as e:
            if "503" in str(e) or "429" in str(e): time.sleep(2); continue
            elif "404" in str(e): continue
    return "My AI servers are a bit busy. Please try again."

def play_voice(text, tld='co.uk'):
    clean = re.sub(r"[*#\[\]_>|`~]", "", text).strip()
    if not clean or len(clean) < 3: return None
    try:
        tts = gTTS(text=clean, lang='en', tld=tld)
        audio = io.BytesIO(); tts.write_to_fp(audio); audio.seek(0)
        return audio
    except: return None

def transcribe_audio(audio_file):
    try:
        audio_bytes = audio_file.read()
        response = client.models.generate_content(model="gemini-1.5-flash", contents=["Transcribe exactly. Return only text.", types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav")])
        return response.text.strip()
    except: return None

def calculate_readiness(user_data):
    gaps = user_data.get("roadmap_data", {}).get("gaps", [])
    high_gaps = sum(1 for g in gaps if g.get("priority") == "High")
    med_gaps = sum(1 for g in gaps if g.get("priority") == "Medium")
    gap_score = max(0, 40 - (high_gaps * 8) - (med_gaps * 4))
    quiz_hist = user_data.get("quiz_scores", [])
    quiz_score = (sum(quiz_hist) / len(quiz_hist) / 100) * 30 if quiz_hist else 15
    int_hist = user_data.get("interview_scores", [])
    int_score = (sum(int_hist) / len(int_hist) / 10) * 30 if int_hist else 15
    total = min(100, max(0, round(gap_score + quiz_score + int_score)))
    return {"total": total, "breakdown": {"Knowledge": f"{round(gap_score)}/40", "Quizzes": f"{round(quiz_score)}/30", "Interviews": f"{round(int_score)}/30"}}

# ==========================================
# 4. STATE INIT & SMART MEMORY
# ==========================================
if "messages" not in st.session_state:
    st.session_state.messages = []
    memory = load_memory()
    if memory:
        st.session_state.user_data = memory
        last_score = memory.get("quiz_scores", [])
        greeting = f"Welcome back! I remember you're preparing for **{memory.get('role', 'your goal')}**. "
        if last_score: greeting += f"Last time, your quiz score was {last_score[-1]}%. Let's beat that today! "
        greeting += "Ready to practice?"
    else:
        st.session_state.user_data = {"step": "ask_role"}
        greeting = "Hello! I'm Maya. Tell me: **what exam or job role are you preparing for?**"
    st.session_state.messages.append({"role": "assistant", "content": greeting, "is_new": True})
st.sidebar.markdown("")
# ==========================================
# 5. SIDEBAR
# ==========================================
with st.sidebar:
    if st.button("🔄 Start New Conversation", use_container_width=True):
        if os.path.exists(PROFILE_FILE): os.remove(PROFILE_FILE)
        st.session_state.clear()
        st.rerun()
    st.divider()

    st.markdown("### 🍅 Focus Mode")
    if "pomo_end" not in st.session_state: st.session_state.pomo_end = None
    
    c1, c2 = st.columns(2)
    if c1.button("Start 25m", use_container_width=True):
        st.session_state.pomo_end = datetime.now() + timedelta(minutes=25); st.rerun()
    if c2.button("Stop", use_container_width=True):
        st.session_state.pomo_end = None; st.rerun()

    if st.session_state.pomo_end:
        if HAS_AUTOREFRESH: st_autorefresh(interval=1000, limit=None, key="pomo")
        remaining = st.session_state.pomo_end - datetime.now()
        if remaining.total_seconds() > 0:
            mins, secs = divmod(int(remaining.total_seconds()), 60)
            st.markdown(f'<div class="timer-box"><div class="timer-text">{mins:02d}:{secs:02d}</div><p style="color:#a78bfa; margin:0;">Deep Work</p></div>', unsafe_allow_html=True)
        else:
            st.success("🎉 Time's up!")
            st.session_state.pomo_end = None
            if HAS_AUTOREFRESH: st_autorefresh(interval=1000000, limit=1)
            
    st.divider()
    st.markdown("### 🎯 Readiness")
    if st.session_state.user_data.get("roadmap_data"):
        result = calculate_readiness(st.session_state.user_data)
        st.metric(label="Score", value=f"{result['total']}/100")
        st.progress(result['total'] / 100)
        quiz_hist = st.session_state.user_data.get("quiz_scores", [])
        if len(quiz_hist) > 0:
            chart_data = pd.DataFrame({"Score": quiz_hist}, index=range(1, len(quiz_hist)+1))
            st.bar_chart(chart_data, height=120, color="#8b5cf6")
        with st.expander("📊 View Roadmap"):
            d = st.session_state.user_data["roadmap_data"]
            for w in d.get("roadmap", []): st.markdown(f"**Wk {w.get('week')}:** {w.get('focus')}")
    else:
        st.info("Setup roadmap to see score.")

    st.divider()
    st.markdown("### 🎮 Modes")
    mode = st.radio("Select Mode:", ["💬 General Coach", "🎤 Voice Interview", "📝 Written Exam", "🧠 Rapid Quiz", "🛠️ Skill Builder"], key="practice_mode")
    if mode == "🎤 Voice Interview": st.info("🎙️ Text input disabled. Use the mic!")
    
    st.divider()
    if st.button("📰 Current Affairs Quiz", use_container_width=True):
        st.session_state.force_news_quiz = True; st.rerun()

    tld = st.selectbox("Maya's Accent", ["co.uk (British)", "com (American)", "com.au (Australian)"])
    voice_tld = tld.split(" ")[0]

# ==========================================
# 6. RENDER CHAT
# ==========================================
for i, msg in enumerate(st.session_state.messages):
    avatar = "🧑‍🏫" if msg["role"] == "assistant" else "🧑"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("is_new"):
            audio = play_voice(msg["content"], tld=voice_tld)
            if audio: st.audio(audio, format="audio/mp3", autoplay=False)
            st.session_state.messages[i]["is_new"] = False

# ==========================================
# 7. SEAMLESS INPUT (With Photo Upload)
# ==========================================
st.write("---")

if mode == "📝 Written Exam" and st.session_state.user_data.get("exam_start_time"):
    elapsed = int((datetime.now() - st.session_state.user_data["exam_start_time"]).total_seconds())
    st.warning(f"⏱️ **Exam Timer:** {elapsed // 60}m {elapsed % 60}s")

uploaded_image = None
if mode in ["📝 Written Exam", "💬 General Coach"]:
    upload_label = "📸 Upload a photo of your answer sheet to be graded" if mode == "📝 Written Exam" else "📸 Upload a photo of a question you are stuck on"
    uploaded_image = st.file_uploader(upload_label, type=["jpg", "jpeg", "png"])
    if uploaded_image:
        st.image(uploaded_image, caption="Your uploaded image", width=300)
        if mode == "💬 General Coach":
            st.info("Maya will analyze this image and help you solve the problem!")

final_input = None
if mode == "🎤 Voice Interview":
    audio_value = st.audio_input("🎤 Record your interview answer...")
    if audio_value:
        with st.spinner("🎧 Transcribing your answer instantly..."):
            transcribed = transcribe_audio(audio_value)
            if transcribed:
                final_input = transcribed
                st.success(f"**You said:** {transcribed}")
                time.sleep(1)
                st.rerun()
else:
    audio_value = st.audio_input("🎤 Or use your voice")
    user_input = st.chat_input("Type your answer here...")
    
    if user_input: final_input = user_input
    elif audio_value:
        with st.spinner("🎧 Transcribing..."):
            transcribed = transcribe_audio(audio_value)
            if transcribed: final_input = transcribed

if uploaded_image:
    if mode == "💬 General Coach":
        final_input = "ANALYZE_DOUBT_IMAGE"
    else:
        final_input = "ANALYZE_EXAM_IMAGE"

if st.session_state.get("force_news_quiz"):
    st.session_state.force_news_quiz = False
    if st.session_state.user_data.get("step") == "coach_mode":
        final_input = "Generate a 3-question current affairs quiz."
        st.session_state.practice_mode = "🧠 Rapid Quiz"

# ==========================================
# 8. AGENT LOGIC
# ==========================================
if final_input and final_input.strip():
    display_text = "📸 [Uploaded an image]" if "IMAGE" in final_input else final_input
    st.session_state.messages.append({"role": "user", "content": display_text})
    
    step = st.session_state.user_data.get("step", "ask_role")
    ai_reply = ""

    with st.spinner("Maya is thinking..."):
        # ONBOARDING
        if step == "ask_role":
            st.session_state.user_data["role"] = final_input
            st.session_state.user_data["step"] = "ask_skills"
            save_memory(st.session_state.user_data)
            ai_reply = get_ai_response(f"User wants to prepare for: '{final_input}'. Acknowledge warmly. Ask about their current background/skills.")

        elif step == "ask_skills":
            st.session_state.user_data["skills"] = final_input
            st.session_state.user_data["step"] = "coach_mode"
            prompt = f"""
            Target: {st.session_state.user_data['role']}. Skills: {final_input}.
            Create 4-week roadmap. Return ONLY JSON:
            {{"readiness_score": <int>, "summary": "<warm>", "gaps": [{{"skill": "", "why": "", "priority": "High|Medium|Low"}}], "roadmap": [{{"week": 1, "focus": "", "tasks": [""]}}]}}
            """
            raw = get_ai_response(prompt, json_mode=True)
            try:
                data = json.loads(raw)
                st.session_state.user_data["roadmap_data"] = data
                save_memory(st.session_state.user_data)
                ai_reply = "I've built your **4-Week Roadmap** (see sidebar). Ready to start practicing?"
            except:
                ai_reply = "I had trouble formatting the roadmap. What are your skills again?"
                st.session_state.user_data["step"] = "ask_skills"

        # READINESS
        elif step == "coach_mode" and any(w in final_input.lower() for w in ["readiness", "ready", "score"]):
            result = calculate_readiness(st.session_state.user_data)
            ai_reply = f"**📊 Readiness: {result['total']}/100**\n\nKnowledge: {result['breakdown']['Knowledge']}\nQuizzes: {result['breakdown']['Quizzes']}\nInterviews: {result['breakdown']['Interviews']}"

        # GENERAL COACH (With Doubt Image Vision)
        elif step == "coach_mode" and mode == "💬 General Coach":
            if final_input == "ANALYZE_DOUBT_IMAGE" and uploaded_image:
                image_bytes = uploaded_image.read()
                prompt = f"""
                You are Maya, a caring AI Coach. The student (preparing for {st.session_state.user_data['role']}) has uploaded a photo of a question they are stuck on.
                1. Transcribe the question you see.
                2. Solve it step-by-step in a warm, encouraging way.
                3. Point out any small mistakes they made if it's visible.
                4. Ask them if they understand the explanation.
                """
                with st.spinner("Maya is reading the question..."):
                    try:
                        response = client.models.generate_content(
                            model="gemini-1.5-flash",
                            contents=[prompt, types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")]
                        )
                        ai_reply = response.text
                    except Exception as e:
                        ai_reply = f"Sorry, I couldn't read the image. Error: {e}"
            else:
                ai_reply = get_ai_response(f"User preparing for {st.session_state.user_data['role']}. They say: '{final_input}'. Respond warmly.")

        # INTERVIEW
        elif step == "coach_mode" and mode == "🎤 Voice Interview":
            if not st.session_state.user_data.get("interview_mode"):
                st.session_state.user_data["interview_mode"] = True
                st.session_state.user_data["interview_turn"] = 0
                st.session_state.user_data["interview_scores"] = []
                ai_reply = "**[Interview Room Started]**\n\n" + (get_ai_response(f"Ask the first interview question for a {st.session_state.user_data['role']} role.") or "Tell me about yourself.")
            else:
                turn = st.session_state.user_data.get("interview_turn", 0)
                role = "HR Manager" if turn % 2 == 0 else "Senior Interviewer"
                ai_reply = get_ai_response(f"You are a {role}. Candidate answered: '{final_input}'. Score /10 using 'Score: X/10'. IF SCORE < 5, pause and explain like a teacher. ELSE, ask next question.")
                st.session_state.user_data["interview_turn"] = turn + 1
                match = re.search(r'(\d+(?:\.\d+)?)\s*/\s*10', ai_reply)
                if match: st.session_state.user_data["interview_scores"].append(float(match.group(1)))
                save_memory(st.session_state.user_data)

        # WRITTEN EXAM (With Exam Image Vision)
        elif step == "coach_mode" and mode == "📝 Written Exam":
            if final_input == "ANALYZE_EXAM_IMAGE" and uploaded_image:
                image_bytes = uploaded_image.read()
                prompt = f"""
                You are a strict but caring examiner. Analyze this handwritten answer sheet for a {st.session_state.user_data['role']} exam.
                Read it line-by-line. 
                1. Transcribe the text you see.
                2. Point out EVERY grammar mistake and punctuation error (missing full stops, commas, etc.).
                3. Grade the content out of 10.
                4. Give one encouraging tip.
                """
                with st.spinner("Maya is grading your handwriting..."):
                    try:
                        response = client.models.generate_content(
                            model="gemini-1.5-flash", 
                            contents=[prompt, types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")]
                        )
                        ai_reply = response.text
                    except Exception as e:
                        ai_reply = f"Sorry, I couldn't read the image. Error: {e}"
            elif not st.session_state.user_data.get("exam_start_time"):
                st.session_state.user_data["exam_start_time"] = datetime.now()
                ai_reply = get_ai_response(f"Generate ONE written exam question for {st.session_state.user_data['role']}. Tell user stopwatch started.")
            else:
                elapsed = int((datetime.now() - st.session_state.user_data["exam_start_time"]).total_seconds())
                st.session_state.user_data["exam_start_time"] = None
                ai_reply = get_ai_response(f"Grade answer: '{final_input}'. Time taken: {elapsed}s. Give /10 and time-management advice.")

        # QUIZ
        elif step == "coach_mode" and mode == "🧠 Rapid Quiz":
            quiz_state = st.session_state.user_data.get("quiz_state", {})
            if "current affairs" in final_input.lower():
                raw = get_ai_response("Generate 1 recent current affairs MCQ. JSON: {'question': '', 'options': ['A', 'B', 'C', 'D'], 'correct_answer': 'A', 'explanation': ''}", json_mode=True)
                try:
                    q = json.loads(raw)
                    st.session_state.user_data["quiz_state"] = {"current_q": q["question"], "options": q["options"], "correct_answer": q["correct_answer"], "explanation": q["explanation"], "answered": False}
                    ai_reply = f"**📰 Current Affairs:**\n{q['question']}\n\n" + "\n".join(q["options"])
                except: ai_reply = "Quiz failed."
            elif quiz_state.get("current_q") and not quiz_state.get("answered"):
                correct = quiz_state.get("correct_answer", "")
                if final_input.strip().upper() in correct.upper():
                    ai_reply = f"✅ **Correct!** {quiz_state.get('explanation', '')}"
                    st.session_state.user_data["quiz_score"] = st.session_state.user_data.get("quiz_score", 0) + 1
                else:
                    ai_reply = f"❌ **Not quite.** Answer was **{correct}**. {quiz_state.get('explanation', '')}"
                
                score_pct = (st.session_state.user_data.get("quiz_score", 0) / 5) * 100
                if "quiz_scores" not in st.session_state.user_data: st.session_state.user_data["quiz_scores"] = []
                st.session_state.user_data["quiz_scores"].append(score_pct)
                
                st.session_state.user_data["quiz_state"]["answered"] = True
                st.session_state.user_data["quiz_state"]["current_q"] = None
                ai_reply += f"\n\nScore: {st.session_state.user_data.get('quiz_score', 0)}/5. Type 'next'."
            else:
                raw = get_ai_response(f"Generate 1 MCQ for {st.session_state.user_data['role']}. JSON: {{'question': '', 'options': ['A', 'B', 'C', 'D'], 'correct_answer': 'A', 'explanation': ''}}", json_mode=True)
                try:
                    q = json.loads(raw)
                    st.session_state.user_data["quiz_state"] = {"current_q": q["question"], "options": q["options"], "correct_answer": q["correct_answer"], "explanation": q["explanation"], "answered": False}
                    ai_reply = f"**Quiz:**\n{q['question']}\n\n" + "\n".join(q["options"])
                except: ai_reply = "Quiz failed."

        # SKILL BUILDER
        elif step == "coach_mode" and mode == "🛠️ Skill Builder":
            ai_reply = get_ai_response(f"User lacks skill: '{final_input}'. Provide 3-step practical micro-project, resource, and ask them to describe step 1.")

    if "IMAGE" in final_input:
        ai_reply = "*(Maya analyzed your image)*\n\n" + ai_reply

    st.session_state.messages.append({"role": "assistant", "content": ai_reply, "is_new": True})
    st.rerun()
