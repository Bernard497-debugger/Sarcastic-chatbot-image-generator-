import os
import re
import requests
from io import BytesIO
from flask import Flask, request, send_file, render_template_string, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)
CORS(app)

# Security & Limits
limiter = Limiter(get_remote_address, app=app, default_limits=["20 per minute"], storage_uri="memory://")

# API Keys (Set these in Render)
UNSPLASH_KEY = os.getenv("UNSPLASH_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")
MODEL_ID = "google/gemini-2.0-flash-001"

# UI Layout
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>SassMaster 3000</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; background: #121212; color: #e0e0e0; display: flex; justify-content: center; padding: 20px; }
        .app-container { width: 100%; max-width: 800px; background: #1e1e1e; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        .nav { display: flex; background: #2d2d2d; border-bottom: 1px solid #333; }
        .nav-btn { flex: 1; padding: 15px; text-align: center; cursor: pointer; border: none; background: none; color: #888; font-weight: bold; transition: 0.3s; }
        .nav-btn.active { color: #007bff; border-bottom: 3px solid #007bff; background: #252525; }
        .panel { padding: 30px; display: none; }
        .panel.active { display: block; }
        
        input { width: 100%; padding: 12px; background: #2d2d2d; border: 1px solid #444; color: white; border-radius: 6px; margin-bottom: 10px; }
        button { width: 100%; padding: 12px; background: #007bff; border: none; color: white; border-radius: 6px; font-weight: bold; cursor: pointer; }
        button:hover { background: #0056b3; }
        
        #chat-log { height: 300px; overflow-y: auto; background: #181818; padding: 15px; border-radius: 8px; margin-bottom: 10px; display: flex; flex-direction: column; }
        .msg { margin: 8px 0; padding: 10px; border-radius: 8px; max-width: 80%; line-height: 1.4; }
        .user { background: #007bff; align-self: flex-end; }
        .bot { background: #333; align-self: flex-start; border-left: 4px solid #ffc107; }
        
        #img-preview { width: 100%; margin-top: 20px; border-radius: 8px; display: none; border: 1px solid #444; }
        .loading { font-style: italic; color: #777; font-size: 0.9em; }
    </style>
</head>
<body>
    <div class="app-container">
        <div class="nav">
            <button class="nav-btn active" onclick="showTab(event, 'chat-tab')">Sarcastic Chat</button>
            <button class="nav-btn" onclick="showTab(event, 'image-tab')">AI Visuals</button>
        </div>

        <div id="chat-tab" class="panel active">
            <div id="chat-log"><div class="msg bot">Oh, another visitor. Try to ask something halfway intelligent, will you?</div></div>
            <input type="text" id="chat-input" placeholder="Type your nonsense here...">
            <button onclick="sendChat()">Send to the Abyss</button>
        </div>

        <div id="image-tab" class="panel">
            <h3>Visual Generator</h3>
            <input type="text" id="img-input" placeholder="Theme (e.g. A dystopian library)">
            <button onclick="generateArt()">Create Masterpiece</button>
            <div id="img-status" class="loading"></div>
            <img id="img-preview" src="">
        </div>
    </div>

    <script>
        function showTab(e, tabId) {
            document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            e.currentTarget.classList.add('active');
        }

        async function sendChat() {
            const input = document.getElementById('chat-input');
            const log = document.getElementById('chat-log');
            if(!input.value) return;

            log.innerHTML += `<div class="msg user">${input.value}</div>`;
            const userMsg = input.value;
            input.value = '';
            log.scrollTop = log.scrollHeight;

            const res = await fetch('/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ message: userMsg })
            });
            const data = await res.json();
            log.innerHTML += `<div class="msg bot">${data.reply}</div>`;
            log.scrollTop = log.scrollHeight;
        }

        async function generateArt() {
            const input = document.getElementById('img-input');
            const img = document.getElementById('img-preview');
            const status = document.getElementById('img-status');
            if(!input.value) return;

            status.innerText = "Consulting the muses (and insulting your taste)...";
            img.style.display = 'none';

            const res = await fetch('/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ theme: input.value })
            });
            const blob = await res.blob();
            img.src = URL.createObjectURL(blob);
            img.style.display = 'block';
            status.innerText = "";
        }
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/chat', methods=['POST'])
def chat():
    msg = request.json.get("message")
    prompt = "You are a sarcastic, witty assistant who thinks they are much smarter than the user. Be condescending but ultimately provide a helpful and kind answer."
    
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
            json={
                "model": MODEL_ID,
                "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": msg}]
            }
        )
        return jsonify({"reply": response.json()['choices'][0]['message']['content']})
    except:
        return jsonify({"reply": "I'm too bored of this conversation to reply correctly."})

@app.route('/generate', methods=['POST'])
def generate():
    theme = request.json.get("theme", "nature")
    
    # 1. Use Gemini to "Enhance" the search query
    try:
        enhance_res = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
            json={
                "model": MODEL_ID,
                "messages": [{"role": "user", "content": f"Give me a 3-word highly descriptive search term for Unsplash based on: {theme}"}]
            }
        )
        search_term = enhance_res.json()['choices'][0]['message']['content'].strip()
    except:
        search_term = theme

    # 2. Fetch from Unsplash
    u_url = f"https://api.unsplash.com/photos/random?query={search_term}&client_id={UNSPLASH_KEY}"
    r = requests.get(u_url).json()
    img_data = requests.get(r['urls']['regular']).content
    
    # 3. Add the sassy label
    img = Image.open(BytesIO(img_data)).convert("RGB").resize((800, 600))
    draw = ImageDraw.Draw(img)
    
    # Font Logic for Docker
    try: font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
    except: font = ImageFont.load_default()
    
    draw.text((30, 520), theme.upper(), font=font, fill="white", stroke_width=2, stroke_fill="black")
    
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)