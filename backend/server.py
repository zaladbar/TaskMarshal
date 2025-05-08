import os
import json
import random
import requests
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from flask_cors import CORS
import openai

# Load persona profiles from JSON
base_dir = os.path.abspath(os.path.dirname(__file__))
personas_file = os.path.join(base_dir, 'personas.json')
with open(personas_file, 'r', encoding='utf-8') as f:
    personas = json.load(f)

# Ensure data directory exists
data_dir = os.path.join(base_dir, 'data')
os.makedirs(data_dir, exist_ok=True)

# Load or initialize preferences
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
    # Save initial prefs to file
    with open(prefs_file, 'w') as f:
        json.dump(prefs, f, indent=4)

# Load or initialize logs
logs_file = os.path.join(data_dir, 'logs.json')
if os.path.exists(logs_file):
    with open(logs_file, 'r') as f:
        try:
            logs = json.load(f)
        except json.JSONDecodeError:
            logs = []
else:
    logs = []
    # Save an empty list to logs file
    with open(logs_file, 'w') as f:
        json.dump(logs, f)

# OpenAI setup
openai_api_key = None
# Try reading from config.json (one level up from base_dir)
config_path = os.path.join(base_dir, '..', 'config.json')
if os.path.exists(config_path):
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            openai_api_key = config.get('openai_api_key')
    except Exception as e:
        print("Warning: Could not read config.json:", e)
# Fallback to environment variable
if not openai_api_key:
    openai_api_key = os.getenv('OPENAI_API_KEY')
if openai_api_key:
    openai.api_key = openai_api_key
    openai_available = True
else:
    openai_available = False
    print("Note: OpenAI API key not found. The app will run without AI-generated messages.")

# Prepare known distraction keywords (for simple classification)
distract_keywords = ["youtube", "facebook", "twitter", "reddit", "instagram", "tiktok", "netflix", "discord", "steam", "game"]

app = Flask(__name__)
CORS(app)  # allow all origins (for Electron local file access)

# Global state for current day session
day_state = None

@app.route('/api/personas', methods=['GET'])
def get_personas():
    # Return list of personas (id, name, icon) for frontend
    result = []
    for pid, pdata in personas.items():
        result.append({
            "id": pid,
            "name": pdata.get("name", pid),
            "icon": pdata.get("icon", "")
        })
    return jsonify(result)

@app.route('/api/prefs', methods=['GET'])
def get_prefs():
    # Return non-sensitive preferences
    return jsonify({
        "consent_given": prefs.get("consent_given", False),
        "last_persona": prefs.get("last_persona", ""),
        "notification_interval": prefs.get("notification_interval", 15)
    })

@app.route('/api/consent', methods=['POST'])
def post_consent():
    # User gives consent
    prefs['consent_given'] = True
    # Save preferences
    try:
        with open(prefs_file, 'w') as f:
            json.dump(prefs, f, indent=4)
    except Exception as e:
        print("Error saving prefs.json:", e)
        return jsonify({"error": "Failed to save preferences"}), 500
    return jsonify({"status": "consent recorded"})

@app.route('/api/start_day', methods=['POST'])
def start_day():
    global day_state
    if day_state is not None:
        return jsonify({"error": "Day already started"}), 400
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    goals = data.get('goals', "")
    persona_id = data.get('persona')
    if not persona_id or persona_id not in personas:
        return jsonify({"error": "Invalid persona"}), 400
    if not prefs.get('consent_given', False):
        # If user somehow tries to start without consent
        return jsonify({"error": "Consent required"}), 403

    # Initialize day state
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
    # Update last_persona in prefs and save
    prefs['last_persona'] = persona_id
    try:
        with open(prefs_file, 'w') as f:
            json.dump(prefs, f, indent=4)
    except Exception as e:
        print("Warning: could not update last_persona in prefs:", e)
    # Optionally provide an initial message (static or persona-based)
    initial_msg = None
    # (For now, no specific initial message beyond frontend default)
    return jsonify({"status": "started", "initial_message": initial_msg})

@app.route('/api/status', methods=['GET'])
def get_status():
    global day_state
    if day_state is None:
        return jsonify({"error": "No active session"}), 400
    # Calculate time since last check
    now = datetime.now(timezone.utc)
    last_check = day_state['last_check']
    period = (now - last_check).total_seconds()
    if period < 1:
        # If called too quickly, return current status without change
        return jsonify({
            "work_time": int(day_state['work_time']),
            "distraction_time": int(day_state['distraction_time']),
            "idle_time": int(day_state['idle_time']),
            "message": ""
        })
    # Query ActivityWatch for events in [last_check, now]
    start_iso = last_check.astimezone(timezone.utc).isoformat()
    end_iso = now.astimezone(timezone.utc).isoformat()
    query_lines = [
        "afk_events = query_bucket(find_bucket('aw-watcher-afk_'));",
        "window_events = query_bucket(find_bucket('aw-watcher-window_'));",
        "window_events = filter_period_intersect(window_events, filter_keyvals(afk_events, 'status', ['not-afk']));",
        "RETURN = merge_events_by_keys(window_events, ['app', 'title']);"
    ]
    payload = {
        "timeperiods": [f"{start_iso}/{end_iso}"],
        "query": query_lines
    }
    try:
        resp = requests.post("http://localhost:5600/api/0/query/", json=payload)
        resp.raise_for_status()
    except requests.RequestException as e:
        print("ActivityWatch query failed:", e)
        return jsonify({"error": "ActivityWatch query failed"}), 500
    try:
        result = resp.json()
    except ValueError as e:
        print("Error parsing ActivityWatch response:", e)
        result = []
    # Expect result to be a list with one element (for the single time period)
    events = []
    if isinstance(result, list) and len(result) > 0:
        events = result[0] if isinstance(result[0], list) else result
    # Sum up durations and classify
    active_duration = 0.0
    distract_duration = 0.0
    for event in events:
        dur = event.get('duration', 0)
        if isinstance(dur, dict) and 'seconds' in dur:
            # In case duration is given as a dict (e.g., from aw-client Event model)
            dur = dur['seconds']
        try:
            dur = float(dur)
        except:
            dur = 0
        if dur <= 0:
            continue
        active_duration += dur
        # Determine if this event is distraction
        app_name = ""; title = ""
        if 'app' in event:
            app_name = str(event['app']).lower()
            title = str(event.get('title', "")).lower()
        elif 'data' in event:
            data = event['data']
            app_name = str(data.get('app', "")).lower()
            title = str(data.get('title', "")).lower()
        text = app_name + " " + title
        for kw in distract_keywords:
            if kw in text:
                distract_duration += dur
                break
    # Calculate idle time in this period
    idle_duration = period - active_duration
    if idle_duration < 0:
        idle_duration = 0
    # Update totals in day_state
    day_state['work_time'] += (active_duration - distract_duration)
    day_state['distraction_time'] += distract_duration
    day_state['idle_time'] += idle_duration
    # Update last_check to now
    day_state['last_check'] = now
    # Handle idle nudge
    message = ""
    if active_duration == 0:  # no activity this entire period
        day_state['idle_streak'] += period
    else:
        # user became active, reset idle streak
        day_state['idle_streak'] = 0
        day_state['idle_nudge_sent'] = False
    idle_threshold = 5 * 60  # e.g., 5 minutes of continuous idle
    if day_state['idle_streak'] >= idle_threshold and not day_state['idle_nudge_sent']:
        # Send idle nudge
        msg_list = day_state['persona']['messages'].get('idle')
        if msg_list:
            message = random.choice(msg_list)
        else:
            message = "You've been idle for a while, let's get back to work."
        day_state['idle_nudge_sent'] = True
    # Handle distraction nudge
    if day_state['distraction_time'] >= day_state['next_distract_nudge']:
        # Time to send a distraction nudge
        persona_profile = day_state['persona']
        goals = day_state.get('goals', "")
        # Determine a specific distraction context (e.g., site or app name)
        top_distraction = None
        top_time = 0
        for event in events:
            # find the distract event with max duration this period (for context)
            app_name = ""; title = ""
            if 'app' in event:
                app_name = str(event['app'])
                title = str(event.get('title', ""))
            elif 'data' in event:
                data = event.get('data', {})
                app_name = str(data.get('app', ""))
                title = str(data.get('title', ""))
            text = f"{app_name} {title}"
            lw = text.lower()
            is_distract = any(kw in lw for kw in distract_keywords)
            dur = event.get('duration', 0)
            try:
                dur = float(dur)
            except:
                dur = 0
            if is_distract and dur > top_time:
                top_time = dur
                # Try to extract site/app name for message
                if "YouTube" in text:
                    top_distraction = "YouTube"
                elif "Facebook" in text:
                    top_distraction = "Facebook"
                elif "Twitter" in text:
                    top_distraction = "Twitter"
                elif "Reddit" in text:
                    top_distraction = "Reddit"
                elif "Instagram" in text:
                    top_distraction = "Instagram"
                elif "Netflix" in text:
                    top_distraction = "Netflix"
                elif "Discord" in text:
                    top_distraction = "Discord"
                elif "Steam" in text:
                    top_distraction = "gaming"  # Steam implies gaming
                elif "game" in text.lower():
                    top_distraction = "gaming"
                else:
                    # default generic if we can't identify
                    top_distraction = "distractions"
        # Compose a nudge message
        if openai_available:
            try:
                # Build prompt for OpenAI
                system_prompt = persona_profile.get('prompt', '')
                # Summarize distraction context
                distract_desc = top_distraction or "non-work activities"
                total_distract_min = int(day_state['distraction_time'] // 60)
                user_message = (f"The user has been distracted by {distract_desc} for about {total_distract_min} minutes. "
                                f"User's goal: {goals if goals else 'not specified'}. As {persona_profile['name']}, give a short motivational nudge to refocus.")
                completion = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    max_tokens=50,
                    temperature=0.7
                )
                chat_response = completion.choices[0].message.content.strip()
                message = chat_response
            except Exception as e:
                print("OpenAI API error during nudge:", e)
                # fallback to static message
                msg_list = persona_profile['messages'].get('distraction')
                if msg_list:
                    message = random.choice(msg_list)
                else:
                    message = "Let's get back on track."
        else:
            msg_list = persona_profile['messages'].get('distraction')
            if msg_list:
                message = random.choice(msg_list)
            else:
                message = "Let's refocus on work."
        # Schedule next nudge threshold
        interval = prefs.get('notification_interval', 15) * 60
        day_state['next_distract_nudge'] += interval
    # Prepare response
    return jsonify({
        "work_time": int(day_state['work_time']),
        "distraction_time": int(day_state['distraction_time']),
        "idle_time": int(day_state['idle_time']),
        "message": message
    })

@app.route('/api/end_day', methods=['GET'])
def end_day():
    global day_state
    if day_state is None:
        return jsonify({"error": "No active session"}), 400
    # Final update from last_check to now (to capture any remaining activity)
    now = datetime.now(timezone.utc)
    last_check = day_state['last_check']
    if now > last_check:
        start_iso = last_check.astimezone(timezone.utc).isoformat()
        end_iso = now.astimezone(timezone.utc).isoformat()
        query_lines = [
            "afk_events = query_bucket(find_bucket('aw-watcher-afk_'));",
            "window_events = query_bucket(find_bucket('aw-watcher-window_'));",
            "window_events = filter_period_intersect(window_events, filter_keyvals(afk_events, 'status', ['not-afk']));",
            "RETURN = merge_events_by_keys(window_events, ['app', 'title']);"
        ]
        payload = {"timeperiods": [f"{start_iso}/{end_iso}"], "query": query_lines}
        try:
            resp = requests.post("http://localhost:5600/api/0/query/", json=payload)
            resp.raise_for_status()
            result = resp.json()
        except Exception as e:
            result = []
        events = result[0] if isinstance(result, list) and len(result) > 0 else []
        active_duration = 0.0
        distract_duration = 0.0
        for event in events:
            dur = event.get('duration', 0)
            try:
                dur = float(dur)
            except:
                dur = 0
            if dur <= 0:
                continue
            active_duration += dur
            text = (str(event.get('app', "")) + " " + str(event.get('title', ""))).lower()
            if any(kw in text for kw in distract_keywords):
                distract_duration += dur
        idle_duration = (now - last_check).total_seconds() - active_duration
        if idle_duration < 0:
            idle_duration = 0
        day_state['work_time'] += (active_duration - distract_duration)
        day_state['distraction_time'] += distract_duration
        day_state['idle_time'] += idle_duration
        day_state['last_check'] = now
    # Prepare final summary
    total_work = int(day_state['work_time'])
    total_distract = int(day_state['distraction_time'])
    total_idle = int(day_state['idle_time'])
    goals = day_state.get('goals', "")
    persona_profile = day_state['persona']
    persona_name = persona_profile['name']
    persona_report = ""
    if openai_available:
        try:
            system_prompt = persona_profile.get('prompt', '')
            def fmt_minutes(sec):
                mins = int(sec // 60)
                hrs = mins // 60
                mins = mins % 60
                if hrs > 0:
                    return f"{hrs}h {mins}m"
                else:
                    return f"{mins}m"
            summary_text = (f"Today, you worked for {fmt_minutes(total_work)} and were distracted for {fmt_minutes(total_distract)}. "
                            f"Idle/break time was {fmt_minutes(total_idle)}. Your goal was: {goals if goals else 'N/A'}.")
            user_message = f"Provide an end-of-day report as {persona_name} commenting on the user's performance. {summary_text}"
            completion = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=150,
                temperature=0.7
            )
            persona_report = completion.choices[0].message.content.strip()
        except Exception as e:
            print("OpenAI API error during end_of_day:", e)
            persona_report = "Great effort today. Keep up the good work!" if total_work >= total_distract else "Remember, tomorrow is a new day to improve your focus."
    else:
        # Simple fallback message
        if total_work >= total_distract:
            persona_report = "Great job today! You stayed focused for most of the day. Keep up the good work!"
        else:
            persona_report = "You had some trouble staying focused today. Let's try to do better tomorrow - I believe in you!"
    # Log the day summary to logs
    log_entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "persona": day_state['persona_id'],
        "goals": goals,
        "work_time": total_work,
        "distraction_time": total_distract,
        "idle_time": total_idle,
        "report": persona_report
    }
    logs.append(log_entry)
    try:
        with open(logs_file, 'w') as f:
            json.dump(logs, f, indent=4)
    except Exception as e:
        print("Error writing logs.json:", e)
    # Clear day_state for next session
    day_state = None
    return jsonify({
        "work_time": total_work,
        "distraction_time": total_distract,
        "idle_time": total_idle,
        "persona_report": persona_report
    })

if __name__ == '__main__':
    # Run the Flask app
    app.run(host='127.0.0.1', port=5000)
