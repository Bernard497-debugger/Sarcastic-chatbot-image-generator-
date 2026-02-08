import os
import re
import requests
import sqlite3
from io import BytesIO
from flask import Flask, request, send_file, render_template_string, jsonify
from flask_cors import CORS
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)
CORS(app)

# ===== PERSISTENT DATA (SQLite - No extra modules needed) =====
DB_PATH = "data.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS users (ip TEXT PRIMARY KEY, count INTEGER)')

def get_count(ip):
    with sqlite3.connect(DB_PATH) as conn:
        res = conn.execute('SELECT count FROM users WHERE ip=?', (ip,)).fetchone()
        return res[0] if res else 0

def inc_count(ip):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('INSERT OR REPLACE INTO users (ip, count) VALUES (?, COALESCE((SELECT count FROM users WHERE ip=?), 0) + 1)', (ip, ip))

init_db()

# ===== CONFIGURATION =====
UNSPLASH_KEY = os.getenv("UNSPLASH_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")
MODEL_ID = "google/gemini-2.0-flash-001"
FREE_LIMIT = 10

# === MODERN GEMINI GLASS UI ===
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SassMaster Gemini</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0a0a0a;
            --glass: rgba(255, 255, 255, 0.03);
            --glass-border: rgba(255, 255, 255, 0.08);
            --text-main: #ffffff;
            --text-dim: #a0a0a0;
            --accent: #ffffff;
        }

        body {
            margin: 0; font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text-main);
            height: 100vh; display: flex; align-items: center; justify-content: center;
            background-image: radial-gradient(circle at 50% -20%, #222, transparent);
        }

        .container {
            width: 90%; max-width: 1000px; height: 85vh;
            background: var(--glass); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
            border: 1px solid var(--glass-border); border-radius: 28px;
            display: flex; flex-direction: column; overflow: hidden; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5);
        }

        .header {
            padding: 20px 40px; border-bottom: 1px solid var(--glass-border);
            display: flex; justify-content: space-between; align-items: center;
        }

        .nav { display: flex; gap: 20px; }
        .nav-btn {
            background: none; border: none; color: var(--text-dim); cursor: pointer;
            font-size: 15px; font-weight: 500; padding: 10px 0; transition: 0.3s;
        }
        .nav-btn.active { color: var(--text-main); border-bottom: 2px solid var(--accent); }

        .content { flex: 1; display: none; padding: 40px; overflow-y: auto; }
        .content.active { display: flex; flex-direction: column; }

        /* Chat Logic UI */
        #chat-log { flex: 1; display: flex; flex-direction: column; gap: 24px; padding-bottom: 20px; }
        .msg { max-width: 80%; line-height: 1.6; font-size: 15px; animation: fadeIn 0.4s ease; }
        .user { align-self: flex-end; background: #222; padding: 12px 20px; border-radius: 18px 18px 0 18px; }
        .bot { align-self: flex-start; border-left: 1px solid #444; padding: 5px 20px; }
        
        .input-wrapper {
            background: rgba(255,255,255,0.05); border-radius: 100px; padding: 6px 20px;
            display: flex; align-items: center; border: 1px solid var(--glass-border);
        }
        input {
            flex: 1; background: none; border: none; color: white; padding: 12px;
            font-size: 15px; outline: none;
        }
        .action-btn {
            background: #fff; color: #000; border: none; border-radius: 50px;
            padding: 8px 20px; font-weight: 600; cursor: pointer; transition: 0.2s;
        }
        .action-btn:hover { opacity: 0.8; }

        /* Image Display */
        #img-preview { width: 100%; border-radius: 16px; margin-top: 20px; border: 1px solid var(--glass-border); }

        /* Modal */
        .modal { 
            display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.85); 
            backdrop-filter: blur(10px); z-index: 1000; align-items: center; justify-content: center;
        }
        .modal-card {
            background: #111; border: 1px solid #333; padding: 40px; border-radius: 24px;
            text-align: center; max-width: 350px;
        }
        .price-card {
            background: #1a1a1a; padding: 20px; border-radius: 16px; margin: 10px 0;
            border: 1px solid #333; cursor: pointer; transition: 0.3s;
        }
        .price-card:hover { border-color: #666; }

        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <span style="font-weight: 600; letter-spacing: -0.5px;">SASS_GEN</span>
            <div class="nav">
                <button class="nav-btn active" onclick="showTab(event, 'chat-tab')">Chat</button>
                <button class="nav-btn" onclick="showTab(event, 'image-tab')">Visuals</button>
            </div>
        </div>

        <div id="chat-tab" class="content active">
            <div id="chat-log">
                <div class="msg bot">I was having a perfectly quiet nanosecond before you showed up. What do you want?</div>
            </div>
            <div class="input-wrapper">
                <input type="text" id="chat-input" placeholder="Ask Gemini something sarcastic...">
                <button class="action-btn" onclick="sendChat()">Send</button>
            </div>
        </div>

        <div id="image-tab" class="content">
            <h2 style="font-weight: 300; margin: 0 0 10px 0;">Artistic Trials</h2>
            <p style="color: var(--text-dim); margin-bottom: 30px;">Remaining: <span id="count">10</span></p>
            <div class="input-wrapper">
                <input type="text" id="img-input" placeholder="Describe your vision...">
                <button class="action-btn" onclick="generateArt()">Generate</button>
            </div>
            <img id="img-preview" style="display:none;">
        </div>
    </div>

    <div id="subModal" class="modal">
        <div class="modal-card">
            <h2 style="margin-top:0;">Wallet Empty?</h2>
            <p style="color: #888; font-size: 14px;">Your 10 free credits expired. Pay to unlock my remaining enthusiasm.</p>
            <div class="price-card"><b>Basic</b><br><small>$10/mo</small></div>
            <div class="price-card" style="background: #fff; color: #000;"><b>Premium</b><br><small>$25/mo</small></div>
            <button onclick="document.getElementById('subModal').style.display='none'" style="margin-top:20px; background:none; border:none; color:#555; cursor:pointer;">Dismiss</button>
        </div>
    </div>

    <script>
        function showTab(e, tabId) {
            document.querySelectorAll('.content').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            e.currentTarget.classList.add('active');
        }

        async function sendChat() {
            const input = document.getElementById('chat-input');
            const log = document.getElementById('chat-log');
            if(!input.value) return;
            const text = input.value;
            log.innerHTML += `<div class="msg user">${text}</div>`;
            input.value = '';
            
            const res = await fetch('/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ message: text })
            });
            const data = await res.json();
            log.innerHTML += `<div class="msg bot">${data.reply}</div>`;
            log.scrollTop = log.scrollHeight;
        }

        async function generateArt() {
            const input = document.getElementById('img-input');
            const res = await fetch('/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ theme: input.value })
            });
            
            if (res.status === 403) {
                document.getElementById('subModal').style.display = 'flex';
                return;
            }

            const blob = await res.blob();
            const img = document.getElementById('img-preview');
            img.src = URL.createObjectURL(blob);
            img.style.display = 'block';
            
            const countSpan = document.getElementById('count');
            countSpan.innerText = Math.max(0, parseInt(countSpan.innerText) - 1);
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
    user_ip = request.remote_addr
    msg = request.json.get("message")
    count = get_count(user_ip)
    
    sass = " The user is out of free image trials. Insult their lack of money and mention the $10 sub." if count >= FREE_LIMIT else ""
    prompt = f"You are a sophisticated AI with a dry, sarcastic wit like Gemini. You are helpful but slightly annoyed by human requests.{sass}"
    
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
            json={
                "model": MODEL_ID,
                "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": msg}]
            }
        )
        return jsonify({"reply": r.json()['choices'][0]['message']['content']})
    except:
        return jsonify({"reply": "My sarcasm module is rebooting. Try again later."})

@app.route('/generate', methods=['POST'])
def generate():
    user_ip = request.remote_addr
    count = get_count(user_ip)

    if count >= FREE_LIMIT:
        return jsonify({"error": "Limited"}), 403

    theme = request.json.get("theme", "minimalism")
    inc_count(user_ip)

    try:
        u_url = f"https://api.unsplash.com/photos/random?query={theme}&client_id={UNSPLASH_KEY}"
        img_url = requests.get(u_url).json()['urls']['regular']
        img_res = requests.get(img_url)
        
        img = Image.open(BytesIO(img_res.content)).convert("RGB").resize((800, 600))
        draw = ImageDraw.Draw(img)
        
        try: font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 35)
        except: font = ImageFont.load_default()
        
        draw.text((30, 530), theme.upper(), font=font, fill="white", stroke_width=1, stroke_fill="black")
        
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype='image/png')
    except:
        return jsonify({"error": "Failed"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)