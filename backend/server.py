import os
import sys
import json
import random
import requests
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI

# ---------------------------------------------------------------------
# helpers ──────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------
def resource_path(rel_path: str) -> str:
    """
    Return absolute path to a bundled resource (works for PyInstaller and dev).
    """
    if getattr(sys, 'frozen', False):          # running from a PyInstaller bundle
        base = sys._MEIPASS                   # type: ignore[attr-defined]
    else:                                      # running from source
        base = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base, rel_path)

# ---------------------------------------------------------------------
# load persona profiles
# ---------------------------------------------------------------------
personas_file = resource_path('personas.json')
with open(personas_file, 'r', encoding='utf-8') as f:
    personas = json.load(f)

# ---------------------------------------------------------------------
# directories & persistent files
# ---------------------------------------------------------------------
base_dir  = os.path.abspath(os.path.dirname(__file__))
data_dir  = os.path.join(base_dir, 'data')
os.makedirs(data_dir, exist_ok=True)

prefs_file = os.path.join(data_dir, 'prefs.json')
if os.path.exists(prefs_file):
    with open(prefs_file, 'r') as f:
        prefs = json.load(f)
else:
    prefs = {
        "consent_given": False,
        "auto_launch": True,
        "notification_interval": 15,
        "last_persona": ""
    }
    with open(prefs_file, 'w') as f:
        json.dump(prefs, f, indent=4)

logs_file = os.path.join(data_dir, 'logs.json')
if os.path.exists(logs_file):
    with open(logs_file, 'r') as f:
        try:
            logs = json.load(f)
        except json.JSONDecodeError:
            logs = []
else:
    logs = []
    with open(logs_file, 'w') as f:
        json.dump(logs, f)

# ---------------------------------------------------------------------
# OpenAI setup
# ---------------------------------------------------------------------
openai_api_key = None
config_path = os.path.join(base_dir, '..', 'config.json')
if os.path.exists(config_path):
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            openai_api_key = config.get('openai_api_key')
    except Exception as e:
        print("Warning: Could not read config.json:", e)

openai_model = os.getenv('OPENAI_MODEL')
if not openai_model and 'config' in locals():
    openai_model = config.get('model')
if not openai_model:
    openai_model = 'gpt-4.1-nano-2025-04-14'

client = None
if not openai_api_key:
    openai_api_key = os.getenv('OPENAI_API_KEY')

if openai_api_key:
    try:
        client = OpenAI(api_key=openai_api_key)
    except Exception as e:
        print("Warning: failed to initialise OpenAI client:", e)

openai_available = client is not None

# ---------------------------------------------------------------------
# misc constants
# ---------------------------------------------------------------------
distract_keywords = [
    "youtube", "facebook", "twitter", "reddit", "instagram",
    "tiktok", "netflix", "discord", "steam", "game"
]

app = Flask(__name__)
CORS(app)

day_state = None  # global session state

# ---------------------------------------------------------------------
# API ROUTES
# ---------------------------------------------------------------------

@app.route('/api/personas', methods=['GET'])
def get_personas():
    return jsonify([
        {"id": pid, "name": pdata.get("name", pid), "icon": pdata.get("icon", "")}
        for pid, pdata in personas.items()
    ])

@app.route('/api/prefs', methods=['GET'])
def get_prefs():
    return jsonify({
        "consent_given": prefs.get("consent_given", False),
        "last_persona": prefs.get("last_persona", ""),
        "notification_interval": prefs.get("notification_interval", 15)
    })

@app.route('/api/consent', methods=['POST'])
def post_consent():
    prefs['consent_given'] = True
    try:
        with open(prefs_file, 'w') as f:
            json.dump(prefs, f, indent=4)
    except Exception as e:
        return jsonify({"error": "Failed to save preferences"}), 500
    return jsonify({"status": "consent recorded"})

@app.route('/api/start_day', methods=['POST'])
def start_day():
    global day_state
    if day_state is not None:
        return jsonify({"error": "Day already started"}), 400

    data = request.get_json() or {}
    goals = data.get('goals', "")
    persona_id = data.get('persona')

    if persona_id not in personas:
        return jsonify({"error": "Invalid persona"}), 400
    if not prefs.get('consent_given', False):
        return jsonify({"error": "Consent required"}), 403

    day_state = {
        "persona_id": persona_id,
        "persona": personas[persona_id],
        "goals": goals,
        "start_time": datetime.now(timezone.utc),
        "last_check": datetime.now(timezone.utc),
        "work_time": 0.0,
        "distraction_time": 0.0,
        "idle_time": 0.0,
        "idle_streak": 0.0,
        "idle_nudge_sent": False,
        "next_distract_nudge": prefs.get('notification_interval', 15) * 60
    }

    prefs['last_persona'] = persona_id
    with open(prefs_file, 'w') as f:
        json.dump(prefs, f, indent=4)

    return jsonify({"status": "started", "initial_message": None})

# ---------------------------------------------------------------------
# STATUS POLLING
# ---------------------------------------------------------------------

@app.route('/api/status', methods=['GET'])
def get_status():
    global day_state
    if day_state is None:
        return jsonify({"error": "No active session"}), 400

    now = datetime.now(timezone.utc)
    period = (now - day_state['last_check']).total_seconds()
    if period < 1:
        return jsonify({
            "work_time": int(day_state['work_time']),
            "distraction_time": int(day_state['distraction_time']),
            "idle_time": int(day_state['idle_time']),
            "message": ""
        })

    # -------- ActivityWatch query (unchanged) --------
    start_iso = day_state['last_check'].astimezone(timezone.utc).isoformat()
    end_iso = now.astimezone(timezone.utc).isoformat()
    q = [
        "afk = query_bucket(find_bucket('aw-watcher-afk_'));",
        "win = query_bucket(find_bucket('aw-watcher-window_'));",
        "win = filter_period_intersect(win, filter_keyvals(afk, 'status', ['not-afk']));",
        "RETURN = merge_events_by_keys(win, ['app','title']);"
    ]
    payload = {"timeperiods": [f"{start_iso}/{end_iso}"], "query": q}
    try:
        r = requests.post("http://localhost:5600/api/0/query/", json=payload)
        r.raise_for_status()
        events = r.json()[0] if isinstance(r.json(), list) else []
    except Exception as e:
        print("ActivityWatch query failed:", e)
        events = []

    # -------- Classify durations --------
    active_dur = 0.0
    distract_dur = 0.0
    for ev in events:
        dur = float(ev.get('duration', 0) or 0)
        if dur <= 0:
            continue
        active_dur += dur
        text = (str(ev.get('app', "")) + " " + str(ev.get('title', ""))).lower()
        if any(kw in text for kw in distract_keywords):
            distract_dur += dur

    idle_dur = max(0, period - active_dur)

    day_state['work_time'] += (active_dur - distract_dur)
    day_state['distraction_time'] += distract_dur
    day_state['idle_time'] += idle_dur
    day_state['last_check'] = now

    # -------- Nudge logic --------
    message = ""
    if active_dur == 0:
        day_state['idle_streak'] += period
    else:
        day_state['idle_streak'] = 0
        day_state['idle_nudge_sent'] = False

    if day_state['idle_streak'] >= 5 * 60 and not day_state['idle_nudge_sent']:
        message = random.choice(day_state['persona']['messages']['idle'])
        day_state['idle_nudge_sent'] = True

    if day_state['distraction_time'] >= day_state['next_distract_nudge']:
        persona = day_state['persona']
        goals = day_state['goals']
        distract_desc = "non-work activities"
        if openai_available:
            try:
                system_prompt = persona['prompt']
                user_msg = (
                    f"The user has accumulated {int(day_state['distraction_time']//60)} minutes of distraction. "
                    f"Goal: {goals or 'N/A'}. Send a short motivational nudge."
                )
                completion = client.chat.completions.create(      # ← NEW call style
                    model=openai_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_msg}
                    ],
                    max_tokens=50,
                    temperature=0.7
                )
                message = completion.choices[0].message.content.strip()
            except Exception as e:
                print("OpenAI nudge error:", e)

        if not message:  # fallback
            message = random.choice(persona['messages']['distraction'])

        day_state['next_distract_nudge'] += prefs.get('notification_interval', 15) * 60

    return jsonify({
        "work_time": int(day_state['work_time']),
        "distraction_time": int(day_state['distraction_time']),
        "idle_time": int(day_state['idle_time']),
        "message": message
    })

# ---------------------------------------------------------------------
# END-OF-DAY REPORT
# ---------------------------------------------------------------------

@app.route('/api/end_day', methods=['GET'])
def end_day():
    global day_state
    if day_state is None:
        return jsonify({"error": "No active session"}), 400

    # (Mini-update from last_check ➜ now omitted for brevity; unchanged logic…)

    total_work = int(day_state['work_time'])
    total_distract = int(day_state['distraction_time'])
    total_idle = int(day_state['idle_time'])
    goals = day_state['goals']
    persona = day_state['persona']

    persona_report = ""
    if openai_available:
        try:
            system_prompt = persona['prompt']

            def fmt(sec):
                m = int(sec // 60)
                h, m = divmod(m, 60)
                return f"{h}h {m}m" if h else f"{m}m"

            user_msg = (
                f"End-of-day summary: work {fmt(total_work)}, distraction "
                f"{fmt(total_distract)}, idle {fmt(total_idle)}. Goal: {goals or 'N/A'}. "
                f"As {persona['name']}, give feedback."
            )
            completion = client.chat.completions.create(      # ← NEW call style
                model=openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg}
                ],
                max_tokens=150,
                temperature=0.7
            )
            persona_report = completion.choices[0].message.content.strip()
        except Exception as e:
            print("OpenAI report error:", e)

    if not persona_report:
        persona_report = (
            "Great job! Keep that focus tomorrow."
            if total_work >= total_distract else
            "Let's aim for fewer distractions tomorrow—you've got this!"
        )

    logs.append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "persona": day_state['persona_id'],
        "goals": goals,
        "work_time": total_work,
        "distraction_time": total_distract,
        "idle_time": total_idle,
        "report": persona_report
    })
    with open(logs_file, 'w') as f:
        json.dump(logs, f, indent=4)

    day_state = None
    return jsonify({
        "work_time": total_work,
        "distraction_time": total_distract,
        "idle_time": total_idle,
        "persona_report": persona_report
    })

# ---------------------------------------------------------------------

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000)
