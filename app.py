import os
import re
import requests
from io import BytesIO
from flask import Flask, request, send_file, render_template_string, jsonify
from flask_cors import CORS
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)
CORS(app)

# ===== CONFIGURATION =====
UNSPLASH_KEY = os.getenv("UNSPLASH_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_KEY")
MODEL_ID = "google/gemini-2.0-flash-001"

# Simple in-memory tracker (Note: Resets on server restart)
user_trials = {}
FREE_LIMIT = 10

# === HTML FRONTEND ===
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
        
        #chat-log { height: 300px; overflow-y: auto; background: #181818; padding: 15px; border-radius: 8px; margin-bottom: 10px; display: flex; flex-direction: column; }
        .msg { margin: 8px 0; padding: 10px; border-radius: 8px; max-width: 80%; line-height: 1.4; }
        .user { background: #007bff; align-self: flex-end; }
        .bot { background: #333; align-self: flex-start; border-left: 4px solid #ffc107; }
        
        .modal { display: none; position: fixed; z-index: 100; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); }
        .modal-content { background: #2d2d2d; margin: 15% auto; padding: 30px; width: 300px; border-radius: 12px; text-align: center; }
        .price-btn { display: block; width: 100%; padding: 10px; margin: 10px 0; background: #28a745; color: white; border-radius: 5px; text-decoration: none; font-weight: bold; }

        input { width: 100%; padding: 12px; background: #2d2d2d; border: 1px solid #444; color: white; border-radius: 6px; margin-bottom: 10px; box-sizing: border-box;}
        button { width: 100%; padding: 12px; background: #007bff; border: none; color: white; border-radius: 6px; font-weight: bold; cursor: pointer; }
    </style>
</head>
<body>
    <div class="app-container">
        <div class="nav">
            <button class="nav-btn active" onclick="showTab(event, 'chat-tab')">Sarcastic Chat</button>
            <button class="nav-btn" onclick="showTab(event, 'image-tab')">AI Visuals</button>
        </div>

        <div id="chat-tab" class="panel active">
            <div id="chat-log"><div class="msg bot">Oh, another visitor. I'm free, unlike your "trial" of artistic talent.</div></div>
            <input type="text" id="chat-input" placeholder="Ask me something...">
            <button onclick="sendChat()">Send</button>
        </div>

        <div id="image-tab" class="panel">
            <h3>Visual Generator (<span id="count">10</span> left)</h3>
            <input type="text" id="img-input" placeholder="Theme...">
            <button onclick="generateArt()">Create Art</button>
            <img id="img-preview" style="width:100%; margin-top:20px; border-radius:8px; display:none;">
        </div>
    </div>

    <div id="subModal" class="modal">
        <div class="modal-content">
            <h2>Trial Ended!</h2>
            <p>You've used all 10 free generations. Time to pay up if you want more "art".</p>
            <a href="#" class="price-btn">Basic: $10/mo</a>
            <a href="#" class="price-btn" style="background:#007bff">Premium: $25/mo</a>
            <button onclick="document.getElementById('subModal').style.display='none'" style="background:none; color:#777;">Maybe later</button>
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
            const input = document.getElementById('img-input');
            const res = await fetch('/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ theme: input.value })
            });
            
            if (res.status === 403) {
                document.getElementById('subModal').style.display = 'block';
                return;
            }

            const blob = await res.blob();
            const img = document.getElementById('img-preview');
            img.src = URL.createObjectURL(blob);
            img.style.display = 'block';
            
            // Update UI count (simple approximation)
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
    
    # Check if user is out of trials to add extra sass
    trial_count = user_trials.get(user_ip, 0)
    extra_sass = ""
    if trial_count >= FREE_LIMIT:
        extra_sass = " The user is out of free image trials, so mock them for being broke and unable to afford the $10 subscription."

    prompt = f"You are a sarcastic assistant. Be witty and condescending but answer accurately.{extra_sass}"
    
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
        return jsonify({"reply": "I'd answer, but my digital brain is more expensive than your free trial."})

@app.route('/generate', methods=['POST'])
def generate():
    user_ip = request.remote_addr
    count = user_trials.get(user_ip, 0)

    if count >= FREE_LIMIT:
        return jsonify({"error": "Subscription Required"}), 403

    theme = request.json.get("theme", "nature")
    user_trials[user_ip] = count + 1

    try:
        # Fetch Image
        u_url = f"https://api.unsplash.com/photos/random?query={theme}&client_id={UNSPLASH_KEY}"
        r = requests.get(u_url).json()
        img_res = requests.get(r['urls']['regular'])
        
        img = Image.open(BytesIO(img_res.content)).convert("RGB").resize((800, 600))
        draw = ImageDraw.Draw(img)
        
        try: font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
        except: font = ImageFont.load_default()
        
        draw.text((30, 520), theme.upper(), font=font, fill="white", stroke_width=2, stroke_fill="black")
        
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype='image/png')
    except:
        return jsonify({"error": "Failed to generate"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)