# Put Arya AI online for everyone (free)

1. Get a free Groq key at https://console.groq.com (API Keys).
2. Create a GitHub account and a new **public** repository (e.g. `arya-ai`).
   Upload the contents of this folder (app.py, requirements.txt, arya_component/, .streamlit/config.toml, README.md).
   Do NOT upload arya.db or any file containing your key.
3. Go to https://share.streamlit.io, sign in with GitHub, click **Create app**.
   - Repository: your repo, Branch: main, Main file: app.py
   - Advanced settings -> App URL: pick a name such as `arya-ai`  ->  https://arya-ai.streamlit.app (if free)
   - Advanced settings -> Secrets: paste `GROQ_API_KEY = "your-key"`
4. Click **Deploy**. Share the link with anyone — no login needed. HTTPS makes the microphone work.

Notes
- Visitors share your Groq free quota. Each visit is limited to 40 messages to protect it.
- Each visitor only sees their own chats and mood.
- For a real name like aryaai.in, buy a domain and follow your registrar's forwarding steps.
