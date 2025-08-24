import os
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai

# ---- Flask App ----
app = Flask(__name__)
CORS(app)

# ---- Gemini Config ----
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)

SYSTEM_INSTRUCTIONS = """
You are an agronomy assistant. Suggest pesticide recommendations and treatment
schedules based on crop, disease, severity, and field details.
Return strictly JSON only.
"""

# ---- Helpers ----
def make_prompt(payload: dict) -> str:
    return f"""
SYSTEM:
{SYSTEM_INSTRUCTIONS}

INPUT:
- plant_name: {payload['plant_name']}
- disease_percentage: {payload['disease_percentage']} %
- previous_fertilizers: {payload.get('previous_fertilizers') or 'None'}
- acres: {payload['acres']}
- location: {payload['location']}
- predicted_class: {payload['predicted_class']}

OUTPUT:
Provide JSON strictly in this format:
{{
  "confidence": 0.9,
  "treatment_schedule": [
    {{
      "product": "Azoxystrobin + Difenoconazole",
      "timing": "Day 0",
      "notes": "Systemic fungicide"
    }},
    {{
      "product": "Mancozeb",
      "timing": "Day 7",
      "notes": "Protectant fungicide"
    }}
  ]
}}
"""

def validate_payload(data):
    required = [
        "plant_name", "disease_percentage", "previous_fertilizers",
        "acres", "location", "predicted_class"
    ]
    missing = [k for k in required if k not in data]
    if missing:
        return False, f"Missing: {', '.join(missing)}"

    try:
        float(data["disease_percentage"])
        float(data["acres"])
    except:
        return False, "disease_percentage and acres must be numbers."

    return True, None

# ---- Routes ----
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat() + "Z"})

@app.route("/recommend", methods=["POST"])
def recommend():
    if not GOOGLE_API_KEY:
        return jsonify({"status": "fail", "error": "Missing GOOGLE_API_KEY env var"}), 500

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "fail", "error": "Expected JSON body"}), 400

    ok, err = validate_payload(data)
    if not ok:
        return jsonify({"status": "fail", "error": err}), 400

    try:
        # Call Gemini
        prompt = make_prompt(data)
        model = genai.GenerativeModel(MODEL_NAME)
        resp = model.generate_content(prompt)
        text = (resp.text or "").strip()

        # Extract JSON safely
        start, end = text.find("{"), text.rfind("}")
        parsed = {}
        if start != -1 and end != -1:
            parsed = json.loads(text[start:end+1])

        treatment_schedule = parsed.get("treatment_schedule", [])

        # Build schedules & pesticides
        schedules = []
        pesticides = []
        today = datetime.utcnow().date()
        for idx, t in enumerate(treatment_schedule, start=1):
            pname = t.get("product", "Unknown")
            pesticides.append(pname)
            schedules.append({
                "pesticide_name": pname,
                "scheduled_date": (today + timedelta(days=(idx-1)*7)).isoformat(),
                "completed": False
            })

        return jsonify({
            "status": "success",
            "pesticides": pesticides,
            "treatment_schedules": schedules
        })

    except Exception as e:
        return jsonify({"status": "fail", "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
