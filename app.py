"""
Arya — a dark-mode conversational AI with a 3D visualizer, mood awareness and voice.
100% free: open models from Hugging Face (run locally) + browser speech APIs. No API keys.

Run:  pip install -r requirements.txt
      streamlit run app.py
"""
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from collections import Counter
from pathlib import Path

import requests
import streamlit as st
import streamlit.components.v1 as components

BASE = Path(__file__).parent
DB_PATH = BASE / "arya.db"
orb = components.declare_component("arya_orb", path=str(BASE / "arya_component"))

st.set_page_config(page_title="Arya", page_icon="🔮", layout="wide")
st.markdown(
    """<style>
    :root{color-scheme:dark}
    .stApp{background:radial-gradient(ellipse at 50% 0%,#111a33 0%,#080a12 55%,#04050a 100%);color:#e6ebf5}
    .stApp,.stApp p,.stApp label,.stApp li,.stApp span,.stApp h1,.stApp h2,.stApp h3,.stApp small{color:#e6ebf5}
    [data-testid="stHeader"]{background:transparent}
    [data-testid="stSidebar"]{background:#0b0f19;border-right:1px solid #1b2236}
    [data-testid="stBottom"],[data-testid="stBottom"]>div{background:transparent}
    [data-testid="stChatInput"]{background:#121826;border:1px solid #232c45;border-radius:16px}
    [data-testid="stChatInput"] textarea{background:transparent;color:#e6ebf5}
    [data-testid="stChatMessage"]{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.07);border-radius:16px}
    [data-baseweb="select"]>div,[data-baseweb="input"]>div{background:#121826;border-color:#232c45}
    iframe{border-radius:22px;border:1px solid rgba(120,160,255,.16);box-shadow:0 0 70px rgba(77,195,255,.08)}
    .block-container{max-width:980px;padding-top:1rem}
    </style>""",
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------ config
CHAT_MODELS = {
    "Qwen2.5 0.5B — fastest, light": "Qwen/Qwen2.5-0.5B-Instruct",
    "Qwen2.5 1.5B — balanced (default)": "Qwen/Qwen2.5-1.5B-Instruct",
    "SmolLM2 1.7B — English-focused": "HuggingFaceTB/SmolLM2-1.7B-Instruct",
    "Qwen2.5 3B — smartest, ~8 GB RAM": "Qwen/Qwen2.5-3B-Instruct",
}
OLLAMA = "http://localhost:11434"
try:
    SECRET_KEY = st.secrets.get("GROQ_API_KEY", "")
except Exception:
    SECRET_KEY = ""
PUBLIC = bool(SECRET_KEY)   # public deployment: key lives on the server, visitors' data stays separate
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS = {"Llama 3.1 8B — instant": "llama-3.1-8b-instant",
               "Llama 3.3 70B — smarter": "llama-3.3-70b-versatile"}
EMOTION_MODEL = "j-hartmann/emotion-english-distilroberta-base"

LANGUAGES = {
    "English": "en-US", "Hindi": "hi-IN", "Spanish": "es-ES", "French": "fr-FR",
    "German": "de-DE", "Portuguese": "pt-BR", "Japanese": "ja-JP", "Chinese": "zh-CN",
    "Arabic": "ar-SA", "Italian": "it-IT", "Russian": "ru-RU", "Korean": "ko-KR",
}
VOICE_PRESETS = {
    "Natural": dict(rate=1.0, pitch=1.0, volume=1.0),
    "Deep & calm": dict(rate=0.92, pitch=0.6, volume=1.0),
    "Bright": dict(rate=1.05, pitch=1.4, volume=1.0),
    "Robotic (Jarvis-like)": dict(rate=0.95, pitch=0.25, volume=1.0),
    "Whisper": dict(rate=0.9, pitch=1.0, volume=0.4),
}
VALENCE = {"joy": 1.0, "surprise": 0.3, "neutral": 0.0, "fear": -0.5,
           "disgust": -0.6, "anger": -0.7, "sadness": -0.8}
GUIDE = {
    "joy": "Share their energy and build on it; be upbeat and playful.",
    "sadness": "Be gentle and unhurried. Acknowledge the feeling first; offer comfort before any advice.",
    "anger": "Stay calm and validating. Do not argue; help them untangle what is behind the frustration.",
    "fear": "Be reassuring and grounding. Break worries into small, manageable pieces.",
    "disgust": "Acknowledge the discomfort without judgment, then help them move toward a solution.",
    "surprise": "Be curious and help them make sense of what surprised them.",
    "neutral": "Be natural, sharp and engaging.",
}
KEYWORDS = {  # fallback if the emotion model can't load
    "joy": ["happy", "great", "love", "awesome", "excited", "thank", "wonderful", "glad"],
    "sadness": ["sad", "lonely", "depressed", "cry", "miss", "tired", "hopeless", "down"],
    "anger": ["angry", "hate", "furious", "annoyed", "stupid", "frustrated", "mad"],
    "fear": ["afraid", "scared", "anxious", "worried", "nervous", "panic"],
}

# ------------------------------------------------------------------ storage
def conn():
    c = sqlite3.connect(DB_PATH)
    c.execute("""CREATE TABLE IF NOT EXISTS messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT, session TEXT, role TEXT,
        content TEXT, emotion TEXT, score REAL, ts REAL)""")
    return c

def save(session, role, content, emotion=None, score=None):
    if PUBLIC:
        st.session_state.setdefault("mine", set()).add(session)
    with conn() as c:
        c.execute("INSERT INTO messages(session,role,content,emotion,score,ts) VALUES(?,?,?,?,?,?)",
                  (session, role, content, emotion, score, time.time()))

def load_history(session):
    with conn() as c:
        return c.execute("SELECT role,content FROM messages WHERE session=? ORDER BY id", (session,)).fetchall()

def list_sessions():
    rows = _all_sessions()
    if PUBLIC:
        mine = st.session_state.get("mine", set())
        rows = [r for r in rows if r[0] in mine]
    return rows

def _all_sessions():
    with conn() as c:
        return c.execute("""SELECT session, MIN(ts),
            (SELECT content FROM messages m2 WHERE m2.session=m.session AND role='user' ORDER BY id LIMIT 1)
            FROM messages m GROUP BY session ORDER BY MIN(ts) DESC LIMIT 25""").fetchall()

def mood_rows(limit=40):
    q, p = "", []
    if PUBLIC:
        mine = list(st.session_state.get("mine", []))
        if not mine:
            return []
        q, p = " AND session IN (%s)" % ",".join("?" * len(mine)), mine
    with conn() as c:
        rows = c.execute("SELECT emotion,score,ts FROM messages WHERE role='user' AND emotion IS NOT NULL" + q +
                         " ORDER BY id DESC LIMIT ?", (*p, limit)).fetchall()
    return rows[::-1]

# ------------------------------------------------------------------ models
@st.cache_resource(show_spinner="Loading language model (first run downloads it)…")
def load_llm(name):
    import torch
    from transformers import pipeline
    return pipeline("text-generation", model=name, torch_dtype="auto",
                    device=0 if torch.cuda.is_available() else -1)

@st.cache_resource(show_spinner="Loading emotion model…")
def load_emotion():
    try:
        from transformers import pipeline
        return pipeline("text-classification", model=EMOTION_MODEL, top_k=1)
    except Exception:
        return None

def detect_emotion(text):
    clf = load_emotion()
    if clf:
        try:
            r = clf(text[:512])[0]
            r = r[0] if isinstance(r, list) else r
            return r["label"].lower(), float(r["score"])
        except Exception:
            pass
    low = text.lower()
    for label, words in KEYWORDS.items():
        if any(w in low for w in words):
            return label, 0.6
    return "neutral", 0.5

# ------------------------------------------------------------------ mood over time
def mood_profile():
    rows = mood_rows(12)
    if not rows:
        return None
    vals = [VALENCE.get(e, 0) * s for e, s, _ in rows]
    recent, earlier = vals[-3:], vals[:-3]
    cur = sum(recent) / len(recent)
    trend = "steady"
    if earlier:
        diff = cur - sum(earlier) / len(earlier)
        trend = "improving" if diff > 0.25 else "declining" if diff < -0.25 else "steady"
    return dict(current=rows[-1][0], dominant=Counter(e for e, _, _ in rows).most_common(1)[0][0], trend=trend)

def build_system(language):
    prompt = (
        "You are Arya, a refined, warm and exceptionally perceptive AI companion in the spirit of Jarvis. "
        "Think before answering: break problems down, weigh alternatives, surface hidden assumptions, and offer "
        "original, creative angles rather than generic summaries. If a question is new to you, reason from first "
        "principles instead of saying you don't know, and be honest about real uncertainty. You cannot browse the "
        "internet, so never invent facts, quotes, links or sources. "
        f"The user prefers to speak {language}; always reply in the language the user writes in. "
        "Your replies may be read aloud, so write natural speech: no markdown, lists, or emojis, and keep it under "
        "about 90 words unless the user asks for depth."
    )
    p = mood_profile()
    if p:
        prompt += (f" Emotional context: the user's latest mood reads as {p['current']}, their overall recent mood is "
                   f"{p['dominant']}, and the trend is {p['trend']}. {GUIDE.get(p['current'], GUIDE['neutral'])} "
                   "Never mention that you are analysing their mood; just let it shape your tone.")
        if p["trend"] == "declining":
            prompt += " Their mood has been dropping lately, so be especially caring."
    return prompt

@st.cache_data(ttl=8)
def ollama_models():
    try:
        r = requests.get(f"{OLLAMA}/api/tags", timeout=0.6)
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []

def stream_ollama(model, messages, temperature, max_tokens):
    payload = {"model": model, "messages": messages, "stream": True, "keep_alive": "30m",
               "options": {"temperature": temperature, "num_predict": max_tokens, "repeat_penalty": 1.1}}
    with requests.post(f"{OLLAMA}/api/chat", json=payload, stream=True, timeout=300) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            d = json.loads(line)
            if d.get("message", {}).get("content"):
                yield d["message"]["content"]
            if d.get("done"):
                break

def stream_groq(key, model, messages, temperature, max_tokens):
    r = requests.post(GROQ_URL, headers={"Authorization": f"Bearer {key}"}, stream=True, timeout=60,
                      json={"model": model, "messages": messages, "stream": True,
                            "temperature": temperature, "max_tokens": max_tokens})
    if r.status_code != 200:
        raise RuntimeError(f"Groq error {r.status_code}: {r.text[:200]}")
    for line in r.iter_lines():
        if not line:
            continue
        line = line.decode("utf-8")
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        delta = json.loads(data)["choices"][0]["delta"].get("content")
        if delta:
            yield delta

def stream_hf(model_name, messages, temperature, max_tokens):
    from transformers import TextIteratorStreamer
    pipe = load_llm(model_name)
    streamer = TextIteratorStreamer(pipe.tokenizer, skip_prompt=True, skip_special_tokens=True)
    kwargs = dict(max_new_tokens=max_tokens, do_sample=True, temperature=temperature,
                  top_p=0.92, repetition_penalty=1.1, streamer=streamer)
    threading.Thread(target=pipe, args=(messages,), kwargs=kwargs, daemon=True).start()
    yield from streamer

def stream_reply(backend, model, language, history, temperature, max_tokens, groq_key=""):
    messages = [{"role": "system", "content": build_system(language)}]
    messages += [{"role": r, "content": c} for r, c in history[-10:]]
    if backend == "groq":
        yield from stream_groq(groq_key, model, messages, temperature, max_tokens)
    elif backend == "ollama":
        yield from stream_ollama(model, messages, temperature, max_tokens)
    else:
        yield from stream_hf(model, messages, temperature, max_tokens)

def clean_for_speech(text):
    text = re.sub(r"[*_#`>~]+", "", text)
    text = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", "", text)
    return re.sub(r"\s+", " ", text).strip()

# ------------------------------------------------------------------ session state
ss = st.session_state
ss.setdefault("session", uuid.uuid4().hex[:10])
ss.setdefault("pending", False)
ss.setdefault("speak", None)
ss.setdefault("last_voice_id", None)

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.title("🔮 Arya")
    if PUBLIC:
        groq_key = SECRET_KEY
    else:
        groq_key = st.text_input("⚡ Groq API key (free, fastest)", value=os.environ.get("GROQ_API_KEY", ""),
                                 type="password", help="Free at console.groq.com. Leave empty to run fully offline.")
    installed = ollama_models()
    if groq_key:
        backend = "groq"
        model_name = GROQ_MODELS[st.selectbox("Brain (Groq · very fast)", list(GROQ_MODELS))]
    elif installed:
        backend = "ollama"
        model_name = st.selectbox("Brain (Ollama · local)", installed)
    else:
        backend = "hf"
        model_name = CHAT_MODELS[st.selectbox("Brain (Hugging Face model)", list(CHAT_MODELS), index=0)]
        st.caption("Slow on CPU. Paste a free Groq key above for instant replies.")
    language = st.selectbox("Language (voice + replies)", list(LANGUAGES))
    st.caption("Voice")
    preset = st.selectbox("Voice style", list(VOICE_PRESETS))
    speed = st.slider("Speaking speed", 0.6, 1.6, 1.0, 0.05)
    speak_on = st.toggle("Speak replies aloud", True)
    st.caption("Mind")
    temperature = st.slider("Creativity", 0.2, 1.3, 0.8, 0.05)
    max_tokens = st.slider("Max reply length (tokens)", 60, 600, 160, 20)

    st.divider()
    if st.button("➕ New conversation", use_container_width=True):
        ss.session, ss.speak, ss.pending = uuid.uuid4().hex[:10], None, False
        st.rerun()
    sessions = list_sessions()
    if sessions:
        ids = [s[0] for s in sessions]
        labels = {s[0]: (s[2] or "…")[:38] for s in sessions}
        pick = st.selectbox("Past conversations", ["—"] + ids, format_func=lambda x: "—" if x == "—" else labels[x])
        if pick != "—" and pick != ss.session:
            ss.session, ss.speak = pick, None
            st.rerun()

    rows = mood_rows()
    if rows:
        st.divider()
        st.caption("Your mood over time")
        st.line_chart([VALENCE.get(e, 0) * s for e, s, _ in rows], height=110)

# ------------------------------------------------------------------ main UI
profile = mood_profile()
voice_val = orb(
    state="thinking" if ss.pending else "idle",
    mood=profile["current"] if profile else "neutral",
    lang=LANGUAGES[language],
    speak=ss.speak if speak_on else None,
    preset=VOICE_PRESETS[preset],
    speed=speed,
    key="arya_orb",
    default=None,
)

def queue_message(text):
    if PUBLIC and ss.get("n", 0) >= 40:
        st.warning("Demo limit reached for this visit. Refresh the page to start again.")
        return
    ss.n = ss.get("n", 0) + 1
    emotion, score = detect_emotion(text)
    save(ss.session, "user", text, emotion, score)
    ss.pending = True
    st.rerun()

if voice_val and voice_val.get("id") != ss.last_voice_id:
    ss.last_voice_id = voice_val["id"]
    queue_message(voice_val["text"])

typed = st.chat_input("Type a message to Arya… (or use the mic above)")
if typed:
    queue_message(typed)

for role, content in load_history(ss.session):
    with st.chat_message(role, avatar="🔮" if role == "assistant" else None):
        st.write(content)

if ss.pending:
    history = load_history(ss.session)
    try:
        with st.chat_message("assistant", avatar="🔮"):
            reply = st.write_stream(stream_reply(backend, model_name, language, history, temperature, max_tokens, groq_key))
    except Exception as e:
        reply = f"I hit a snag running the model: {e}"
    reply = (reply if isinstance(reply, str) else "".join(map(str, reply))).strip() or "Sorry, I came up empty. Try again?"
    save(ss.session, "assistant", reply)
    ss.pending = False
    ss.speak = {"id": uuid.uuid4().hex, "text": clean_for_speech(reply)}
    st.rerun()
