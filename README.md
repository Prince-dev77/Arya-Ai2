# Arya — free, no-API-key AI companion (Streamlit)

```bash
pip install -r requirements.txt
streamlit run app.py
```

- **Brain:** open Hugging Face models run locally (pick one in the sidebar; first use downloads it).
- **Mood awareness:** `j-hartmann/emotion-english-distilroberta-base` tags each message; Arya tracks the trend over time and adapts tone.
- **Voice:** browser speech recognition + speech synthesis (use Chrome or Edge). 12 languages, voice picker, style presets, speed control, hands-free mode.
- **3D visualizer:** Three.js orb that reacts to listening / thinking / speaking, follows your pointer, and tints to your mood.
- **History:** SQLite (`arya.db`) — past conversations in the sidebar.
- Works on CPU; a GPU makes replies much faster. Mic access needs `localhost` or HTTPS.

## Fast replies (recommended)
Install [Ollama](https://ollama.com) (free, local), then:

```bash
ollama pull qwen2.5:1.5b      # quick; or llama3.2:3b / qwen2.5:3b if you have a GPU
```
Arya auto-detects Ollama and streams the reply word by word. Without Ollama it falls back to Hugging Face models (slower on CPU).

## Instant replies with Groq (optional, free key)
1. Create a free account at https://console.groq.com and make an API key (no card needed).
2. Paste it into the "Groq API key" box in Arya's sidebar — or set it once: `set GROQ_API_KEY=your_key` (Windows) / `export GROQ_API_KEY=your_key` (Mac/Linux) before `streamlit run app.py`.
Replies then stream at several hundred words per second. Note your messages are sent to Groq's servers when you use this.
