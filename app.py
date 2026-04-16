import os
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
import google.generativeai as genai
from flask_cors import CORS
import requests

BASE_DIR = Path(__file__).resolve().parent
# Ensure this points to the folder containing your index.html
FRONTEND_DIR = (BASE_DIR.parent / "externship").resolve()

load_dotenv(BASE_DIR / ".env")

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
CORS(app) # Handles cross-origin requests from Vercel

conversation_history = []

def get_gemini_api_key():
    return (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()

def get_model_candidates():
    preferred = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()
    return [preferred, "gemini-1.5-flash", "gemini-pro"]

def get_supabase_config():
    return {
        "url": os.getenv("SUPABASE_URL", "").strip(),
        "key": os.getenv("API_KEY", "").strip(),
        "table": os.getenv("SUPABASE_CHAT_TABLE", "chat_messages").strip(),
    }

def save_message_to_db(role: str, text: str):
    config = get_supabase_config()
    if not config["url"] or not config["key"]: return
    try:
        endpoint = f"{config['url'].rstrip('/')}/rest/v1/{config['table']}"
        headers = {
            "apikey": config["key"],
            "Authorization": f"Bearer {config['key']}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        requests.post(endpoint, headers=headers, json={"role": role, "text": text}, timeout=10)
    except Exception as e:
        print(f"DB Error: {e}")

@app.route('/api/data', methods=['GET'])
def get_data():
    return jsonify({"message": "Online! Connected to Railway."})

@app.route("/")
def serve_index():
    return send_from_directory(app.static_folder, "index.html")

@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory(app.static_folder, path)

@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(silent=True) or {}
    user_text = data.get("text", "").strip()

    if not user_text:
        return jsonify({"error": "No text provided"}), 400

    api_key = get_gemini_api_key()
    if not api_key:
        return jsonify({"error": "API Key missing on backend"}), 500

    # Save User Message
    conversation_history.append({"role": "user", "text": user_text})
    save_message_to_db("user", user_text)

    try:
        genai.configure(api_key=api_key)
        ai_text = "I'm sorry, I couldn't process that."
        
        for model_name in get_model_candidates():
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(user_text)
                ai_text = response.text
                break
            except Exception:
                continue

        # Save AI Message
        conversation_history.append({"role": "ai", "text": ai_text})
        save_message_to_db("ai", ai_text)
        
        return jsonify({"reply": ai_text})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
