import os
import re
import requests
from io import BytesIO
from flask import Flask, request, send_file, render_template_string, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)
CORS(app)

# ===== DATABASE CONFIG =====
db_url = os.environ.get("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///local.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.String(50), primary_key=True)
    trials = db.Column(db.Integer, default=0)

with app.app_context():
    db.create_all()

# ===== API CONFIG =====
UNSPLASH_KEY = os.getenv("UNSPLASH_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")
MODEL_ID = "google/gemini-2.0-flash-001"
FREE_LIMIT = 10

# === MODERN GEMINI-STYLE UI ===
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gemini Sass Studio</title>
    <style>
        :root {
            --bg: #070809;
            --glass: rgba(255, 255, 255, 0.05);
            --border: rgba(255, 255, 255, 0.1);
            --accent: linear-gradient(135deg, #4285f4, #9b72cb, #d96570);
            --text: #e8eaed;
        }
        body {
            margin: 0; font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text);
            background-image: radial-gradient(circle at 0% 0%, #1a237e 0%, transparent 40%),
                              radial-gradient(circle at 100% 100%, #4a148c 0%, transparent 40%);
            min-height: 100vh; display: flex; align-items: center; justify-content: center;
        }
        .container {
            width: 90%; max-width: 900px; height: 80vh; display: flex; flex-direction: column;
            background: var(--glass); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
            border: 1px solid var(--border); border-radius: 24px; overflow: hidden;
        }
        .header { padding: 20px; text-align: center; border-bottom: 1px solid var(--border); font-size: 1.2rem; font-weight: 600; letter-spacing: 1px; }
        .tabs { display: flex; background: rgba(0,0,0,0.2); }
        .tab-btn { flex: 1; padding: 15px; border: none; background: none; color: #9aa0a6; cursor: pointer; transition: 0.3s; font-weight: 500; }
        .tab-btn.active { color: white; background: var(--glass); box-shadow: inset 0 -2px 0 #4285f4; }
        
        .content { flex: 1; overflow-y: auto; padding: 20px; display: none; }
        .content.active { display: flex; flex-direction: column; }

        /* Chat UI */
        #chat-log { flex: 1; display: flex; flex-direction: column; gap: 15px; padding-bottom: 20px; }
        .msg { padding: 12px 16px; border-radius: 18px; max-width: 80%; line-height: 1.5; font-size: 0.95rem; }
        .user { align-self: flex-end; background: #3c4043; border-bottom-right-radius: 4px; }
        .bot { align-self: flex-start; background: rgba(66, 133, 244, 0.15); border: 1px solid rgba(66, 133, 244, 0.3); border-bottom-left-radius: 4px; }
        
        .input-area { display: flex; gap: 10px; background: rgba(0,0,0,0.3); padding: 15px; border-top: 1px solid var(--border); }
        input { flex: 1; background: #202124; border: 1px solid var(--border); border-radius: 12px; padding: 12px; color: white; outline: none; }
        button.send-btn { background: var(--accent); border: none; border-radius: 12px; padding: 0 20px; color: white; cursor: pointer; font-weight: 600; }

        /* Modal */
        .modal { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.8); align-items: center; justify-content: center; z-index: 1000; }
        .modal-card { background: #202124; padding: 30px; border-radius: 20px; text-align: center; width: 320px; border: 1px solid var(--border); }
        .price { font-size: 2rem; font-weight: bold; margin: 15px 0; display: block; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">Gemini Sass Studio</div>
        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('chat')">Chatbot</button>
            <button class="tab-btn" onclick="switchTab('gen')">Art Gen</button>
        </div>

        <div id="chat" class="content active">
            <div id="chat-log"><div class="msg bot">Ask me something. If it's dumb, I'll tell you.</div></div>
            <div class="input-area">
                <input type="text" id="chat-input" placeholder="Message Gemini Sass...">
                <button class="send-btn" onclick="sendChat()">Send</button>
            </div>
        </div>

        <div id="gen" class="content">
            <div id="gen-box" style="flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center;">
                <p id="trial-text">10 free generations left</p>
                <img id="art-preview" style="max-width:100%; border-radius:12px; display:none; margin-bottom: 20px;">
                <div class="input-area" style="width:100%; border:none;">
                    <input type="text" id="art-input" placeholder="Imagine something...">
                    <button class="send-btn" onclick="generateArt()">Create</button>
                </div>
            </div>
        </div>
    </div>

    <div id="paywall" class="modal">
        <div class="modal-card">
            <h3>Trial Ended</h3>
            <p>You're out of freebies. Time to act like a pro.</p>
            <div style="background:var(--glass); padding:15px; border-radius:12px; margin: 10px 0;">
                <span style="font-size:0.8rem; color:#888;">BASIC</span>
                <span class="price">$10</span>
            </div>
            <div style="background:var(--accent); padding:15px; border-radius:12px; margin: 10px 0;">
                <span style="font-size:0.8rem; color:white;">PREMIUM</span>
                <span class="price" style="color:white;">$25</span>
            </div>
            <button onclick="closeModal()" style="background:none; border:none; color:#5f6368; cursor:pointer;">Dismiss</button>
        </div>
    </div>

    <script>
        function switchTab(id) {
            document.querySelectorAll('.content').forEach(c => c.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.getElementById(id).classList.add('active');
            event.currentTarget.classList.add('active');
        }

        async function sendChat() {
            const input = document.getElementById('chat-input');
            const log = document.getElementById('chat-log');
            if(!input.value) return;
            log.innerHTML += `<div class="msg user">${input.value}</div>`;
            const res = await fetch('/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ message: input.value })
            });
            const data = await res.json();
            log.innerHTML += `<div class="msg bot">${data.reply}</div>`;
            input.value = '';
            log.scrollTop = log.scrollHeight;
        }

        async function generateArt() {
            const input = document.getElementById('art-input');
            const res = await fetch('/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ theme: input.value })
            });
            if (res.status === 403) {
                document.getElementById('paywall').style.display = 'flex';
                return;
            }
            const blob = await res.blob();
            const preview = document.getElementById('art-preview');
            preview.src = URL.createObjectURL(blob);
            preview.style.display = 'block';
        }
        function closeModal() { document.getElementById('paywall').style.display='none'; }
    </script>
</body>
</html>
"""

# 

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/chat', methods=['POST'])
def chat():
    user_ip = request.remote_addr
    user = User.query.get(user_ip)
    sass_level = ""
    if user and user.trials >= FREE_LIMIT:
        sass_level = " IMPORTANT: The user is broke and out of trials. Remind them they need to subscribe for $10 to get more art."

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
            json={
                "model": MODEL_ID,
                "messages": [{"role": "system", "content": f"You are a sarcastic but kind AI. Be witty.{sass_level}"}, 
                             {"role": "user", "content": request.json.get("message")}]
            }
        )
        return jsonify({"reply": response.json()['choices'][0]['message']['content']})
    except:
        return jsonify({"reply": "Even my error messages are better than your prompts."})

@app.route('/generate', methods=['POST'])
def generate():
    user_ip = request.remote_addr
    user = User.query.get(user_ip)
    if not user:
        user = User(id=user_ip, trials=0)
        db.session.add(user)
    
    if user.trials >= FREE_LIMIT:
        return jsonify({"error": "Pay up"}), 403

    theme = request.json.get("theme", "abstract")
    try:
        u_url = f"https://api.unsplash.com/photos/random?query={theme}&client_id={UNSPLASH_KEY}"
        img_url = requests.get(u_url).json()['urls']['regular']
        img_data = requests.get(img_url).content
        img = Image.open(BytesIO(img_data)).convert("RGB").resize((800, 600))
        
        user.trials += 1
        db.session.commit()
        
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype='image/png')
    except:
        return jsonify({"error": "Failed"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)