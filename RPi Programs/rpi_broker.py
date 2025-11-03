# rpi_broker.py
# Run: python3 rpi_broker.py
import json
import time
import threading
import requests
from flask import Flask, render_template_string, request, redirect, url_for, flash
import paho.mqtt.client as mqtt
import os

# -------------------------
# Load config
# -------------------------
CONFIG_PATH = "config.json"
if not os.path.exists(CONFIG_PATH):
    raise SystemExit("config.json missing. Copy the provided config file and edit values.")

with open(CONFIG_PATH, "r") as f:
    cfg = json.load(f)

FIREBASE_URL = cfg["firebase"]["database_url"].rstrip("/")
MQTT_BROKER = cfg["mqtt"]["broker_ip"]
MQTT_PORT = int(cfg["mqtt"].get("port", 1883))
ALLOWED_UIDS = set(u.upper() for u in cfg.get("allowed_uids", []))
DEVICES = cfg["devices"]

# Topics - UPDATED TO MATCH ESP32
TOPIC_NFC_SCAN = "esp/nfc/scan"              # ESP publishes NFC scans here
TOPIC_NFC_RESPONSE = "esp/nfc/response"      # Broker responds here
TOPIC_WEATHER_SENSOR = "esp/weather/sensor"  # ESP publishes temp/humidity
TOPIC_WEATHER_STATUS = "esp/weather/status"  # ESP publishes device status
TOPIC_WEATHER_CONTROL = "esp/weather/control" # Broker sends commands here

# Keep old topics for backward compatibility if needed
TOPIC_LIGHT_STATUS = "esp/light/status"
TOPIC_LIGHT_CMD = "esp/light/cmd"

# Simple in-memory state (mirrors config devices)
state = {
    "door_lock": dict(DEVICES.get("door_lock", {})),
    "room_control": dict(DEVICES.get("room_control", {}))
}

# -------------------------
# Firebase helpers
# -------------------------
def fb_put(path, payload):
    """
    PUT data to Firebase RTDB (overwrites). path: e.g. /devices/door_lock.json
    Note: this uses unauthenticated REST. Secure your DB in production.
    """
    url = f"{FIREBASE_URL}{path}.json"
    try:
        r = requests.put(url, json=payload, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print("[FB PUT ERROR]", e)
        return None

def fb_patch(path, payload):
    url = f"{FIREBASE_URL}{path}.json"
    try:
        r = requests.patch(url, json=payload, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print("[FB PATCH ERROR]", e)
        return None

def fb_get(path):
    url = f"{FIREBASE_URL}{path}.json"
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print("[FB GET ERROR]", e)
        return None

# -------------------------
# Ensure initial schema
# -------------------------
def ensure_schema():
    base = "/devices"
    existing = fb_get(base)
    if existing is None:
        # create default skeleton
        skeleton = {
            "door_lock": {
                "device_id": "door_lock",
                "status": state["door_lock"].get("status", "locked"),
                "last_userid": state["door_lock"].get("last_userid", None),
                "updated_at": int(time.time())
            },
            "room_control": {
                "device_id": "room_control",
                "temperature": None,
                "humidity": None,
                "light_mode": state["room_control"].get("light_mode", "off"),
                "last_userid": state["room_control"].get("last_userid", None),
                "updated_at": int(time.time())
            }
        }
        print("[INFO] Creating Firebase schema...")
        fb_put(base, skeleton)
    else:
        print("[INFO] Firebase schema exists.")

# -------------------------
# MQTT Handlers
# -------------------------
def on_connect(client, userdata, flags, rc):
    print("[MQTT] Connected with rc=", rc)
    # UPDATED SUBSCRIPTIONS
    client.subscribe([
        (TOPIC_NFC_SCAN, 0),
        (TOPIC_WEATHER_SENSOR, 0),
        (TOPIC_WEATHER_STATUS, 0),
        (TOPIC_LIGHT_STATUS, 0)
    ])
    print("[MQTT] Subscribed to topics:")
    print(f"  - {TOPIC_NFC_SCAN}")
    print(f"  - {TOPIC_WEATHER_SENSOR}")
    print(f"  - {TOPIC_WEATHER_STATUS}")
    print(f"  - {TOPIC_LIGHT_STATUS}")

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        topic = msg.topic
        print(f"[MQTT] {topic} -> {payload}")
        data = json.loads(payload)
    except Exception as e:
        print("[MQTT] Bad message:", e)
        return

    if topic == TOPIC_NFC_SCAN:
        handle_nfc_scan(data)
    elif topic == TOPIC_WEATHER_SENSOR:
        handle_weather_sensor(data)
    elif topic == TOPIC_WEATHER_STATUS:
        handle_weather_status(data)
    elif topic == TOPIC_LIGHT_STATUS:
        handle_light_status(data)

def handle_nfc_scan(data):
    """
    UPDATED: Handle NFC scan from esp/nfc/scan
    expected data:
    {
      "device_id":"esp32_weather_nfc_01",
      "nfc_uid":"A1B2C3D4",
      "action":"scan",
      "timestamp":12345
    }
    """
    uid = str(data.get("nfc_uid","")).upper()
    device_id = data.get("device_id", "unknown")
    
    if uid == "":
        print("[NFC] Empty UID")
        return

    now = int(time.time())

    print(f"\n{'='*50}")
    print(f"[NFC SCAN] Device: {device_id}")
    print(f"[NFC SCAN] UID: {uid}")
    print(f"[NFC SCAN] Checking access...")

    # Check allowed_uids
    approved = uid in ALLOWED_UIDS
    if approved:
        print(f"[ACCESS] ✓ UID {uid} AUTHORIZED - Granting access")
        # update last_userid in memory and firebase
        state["door_lock"]["last_userid"] = uid
        state["door_lock"]["status"] = "unlocked"
        state["door_lock"]["updated_at"] = now
        state["room_control"]["last_userid"] = uid  # user now in room
        state["room_control"]["updated_at"] = now

        # Update firebase
        fb_patch("/devices/door_lock", {
            "status": "unlocked",
            "last_userid": uid,
            "updated_at": now
        })
        fb_patch("/devices/room_control", {
            "last_userid": uid,
            "updated_at": now
        })

        # UPDATED: Send grant response to esp/nfc/response
        resp = {
            "access": "granted", 
            "nfc_uid": uid,
            "device_id": device_id,
            "timestamp": now
        }
        mqtt_client.publish(TOPIC_NFC_RESPONSE, json.dumps(resp))
        print(f"[MQTT] ✓ Published ACCESS GRANTED to {TOPIC_NFC_RESPONSE}")
    else:
        print(f"[ACCESS] ✗ UID {uid} DENIED - Not in allowed list")
        # send deny
        resp = {
            "access": "denied", 
            "nfc_uid": uid,
            "device_id": device_id,
            "timestamp": now
        }
        mqtt_client.publish(TOPIC_NFC_RESPONSE, json.dumps(resp))
        print(f"[MQTT] ✗ Published ACCESS DENIED to {TOPIC_NFC_RESPONSE}")
        # log to firebase
        fb_patch("/devices/door_lock", {
            "last_attempt": uid,
            "last_attempt_at": now
        })
    print(f"{'='*50}\n")

def handle_weather_sensor(data):
    """
    UPDATED: Handle weather sensor data from esp/weather/sensor
    expected:
    {
      "device_id":"esp32_weather_nfc_01",
      "temperature": 26.5,
      "humidity": 58.2,
      "timestamp": 12345
    }
    """
    temp = data.get("temperature")
    hum = data.get("humidity")
    device_id = data.get("device_id", "unknown")
    now = int(time.time())
    
    if temp is not None or hum is not None:
        state["room_control"]["temperature"] = temp
        state["room_control"]["humidity"] = hum
        state["room_control"]["updated_at"] = now
        state["room_control"]["device_id"] = device_id
        
        # update firebase device node
        fb_patch("/devices/room_control", {
            "temperature": temp,
            "humidity": hum,
            "device_id": device_id,
            "updated_at": now
        })
        print(f"[SENSOR] 🌡️ Temp: {temp}°C | 💧 Humidity: {hum}% | Device: {device_id}")

def handle_weather_status(data):
    """
    UPDATED: Handle device status from esp/weather/status
    expected:
    {
      "device_id":"esp32_weather_nfc_01",
      "status":"online",
      "wifi_rssi":-45,
      "nfc_available":true,
      "display_available":true,
      "uptime":12345
    }
    """
    device_id = data.get("device_id", "unknown")
    status = data.get("status", "unknown")
    now = int(time.time())
    
    print(f"\n[STATUS] Device: {device_id}")
    print(f"         Status: {status}")
    print(f"         WiFi RSSI: {data.get('wifi_rssi')} dBm")
    print(f"         NFC Available: {data.get('nfc_available')}")
    print(f"         Display Available: {data.get('display_available')}")
    print(f"         Uptime: {data.get('uptime')} seconds\n")
    
    # Store device status in Firebase
    fb_patch(f"/devices/{device_id}/status", {
        "online": status == "online",
        "wifi_rssi": data.get("wifi_rssi"),
        "nfc_available": data.get("nfc_available"),
        "display_available": data.get("display_available"),
        "uptime": data.get("uptime"),
        "last_seen": now
    })

def handle_light_status(data):
    """
    expected:
    { "device_id":"light", "mode":"off" / "low"/"med"/"high" }
    """
    mode = data.get("mode")
    now = int(time.time())
    if mode:
        state["room_control"]["light_mode"] = mode
        state["room_control"]["updated_at"] = now
        fb_patch("/devices/room_control", {"light_mode": mode, "updated_at": now})
        print(f"[LIGHT] 💡 Mode updated: {mode}")

# -------------------------
# MQTT client setup
# -------------------------
mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

def mqtt_loop():
    print(f"[MQTT] Connecting to broker at {MQTT_BROKER}:{MQTT_PORT}...")
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_forever()

# -------------------------
# Flask web app
# -------------------------
app = Flask(__name__)
app.secret_key = "replace_with_a_random_string_for_prod"

DASH_TEMPLATE = """
<!doctype html>
<html>
<head>
  <title>Smart Room Dashboard</title>
  <meta http-equiv="refresh" content="30">
  <meta charset="UTF-8">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { 
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      padding: 20px;
      min-height: 100vh;
    }
    .container { 
      max-width: 1000px; 
      margin: auto; 
      background: white; 
      padding: 30px; 
      border-radius: 15px; 
      box-shadow: 0 10px 40px rgba(0,0,0,0.2);
    }
    h2 { 
      color: #333; 
      margin-bottom: 20px;
      font-size: 32px;
      text-align: center;
    }
    .status-bar {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      padding: 15px;
      border-radius: 10px;
      margin: 20px 0;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .status-bar .user {
      font-size: 18px;
      font-weight: bold;
    }
    .status-bar .door {
      background: rgba(255,255,255,0.2);
      padding: 8px 15px;
      border-radius: 20px;
    }
    .sensor-grid { 
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 20px; 
      margin: 30px 0; 
    }
    .sensor-card { 
      background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
      padding: 25px; 
      border-radius: 15px;
      color: white;
      text-align: center;
      box-shadow: 0 5px 15px rgba(0,0,0,0.1);
      transition: transform 0.3s;
    }
    .sensor-card:hover {
      transform: translateY(-5px);
    }
    .sensor-card h3 { 
      font-size: 16px; 
      margin-bottom: 10px;
      opacity: 0.9;
    }
    .sensor-card .value { 
      font-size: 42px; 
      font-weight: bold;
      margin: 10px 0;
    }
    .sensor-card.temp {
      background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
    }
    .sensor-card.humid {
      background: linear-gradient(135deg, #30cfd0 0%, #330867 100%);
    }
    .sensor-card.light {
      background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%);
      color: #333;
    }
    .control-panel {
      background: #f8f9fa;
      padding: 25px;
      border-radius: 10px;
      margin: 30px 0;
    }
    .control-panel h3 {
      color: #333;
      margin-bottom: 20px;
      font-size: 20px;
    }
    .form-group { 
      margin: 15px 0; 
    }
    .form-group label {
      display: block;
      color: #555;
      font-weight: 600;
      margin-bottom: 8px;
    }
    input, select { 
      padding: 12px; 
      margin: 5px 0;
      border: 2px solid #ddd;
      border-radius: 8px;
      font-size: 16px;
      width: 100%;
      max-width: 400px;
    }
    input:focus, select:focus {
      outline: none;
      border-color: #667eea;
    }
    button { 
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white; 
      border: none; 
      border-radius: 8px; 
      cursor: pointer;
      padding: 12px 30px;
      font-size: 16px;
      font-weight: 600;
      margin-top: 10px;
      transition: all 0.3s;
    }
    button:hover { 
      transform: translateY(-2px);
      box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
    }
    .flash { 
      background: #fff3cd; 
      border-left: 4px solid #ffc107;
      padding: 15px; 
      margin: 15px 0; 
      border-radius: 5px;
      color: #856404;
    }
    .flash.success {
      background: #d4edda;
      border-left-color: #28a745;
      color: #155724;
    }
    .flash.error {
      background: #f8d7da;
      border-left-color: #dc3545;
      color: #721c24;
    }
    .footer {
      text-align: center;
      margin-top: 30px;
      color: #666;
      font-size: 14px;
    }
    .allowed-uids {
      background: #e7f3ff;
      padding: 15px;
      border-radius: 8px;
      margin: 20px 0;
    }
    .allowed-uids h4 {
      color: #0066cc;
      margin-bottom: 10px;
    }
    .uid-list {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    .uid-tag {
      background: white;
      padding: 5px 12px;
      border-radius: 15px;
      font-family: monospace;
      font-size: 14px;
      border: 2px solid #0066cc;
    }
  </style>
</head>
<body>
  <div class="container">
    <h2>🏠 Smart Room Dashboard</h2>
    
    <div class="status-bar">
      <div class="user">
        👤 Current User: <strong>{{ last_user }}</strong>
      </div>
      <div class="door">
        🚪 Door: <strong>{{ door_status|upper }}</strong>
      </div>
    </div>
    
    <div class="sensor-grid">
      <div class="sensor-card temp">
        <h3>🌡️ Temperature</h3>
        <div class="value">{{ temp }}</div>
        <div>degrees Celsius</div>
      </div>
      
      <div class="sensor-card humid">
        <h3>💧 Humidity</h3>
        <div class="value">{{ hum }}</div>
        <div>percent</div>
      </div>
      
      <div class="sensor-card light">
        <h3>💡 Light</h3>
        <div class="value">{{ light|upper }}</div>
        <div>current mode</div>
      </div>
    </div>

    <div class="allowed-uids">
      <h4>📋 Authorized NFC Cards</h4>
      <div class="uid-list">
        {% for uid in allowed_uids %}
        <span class="uid-tag">{{ uid }}</span>
        {% endfor %}
      </div>
    </div>

    <div class="control-panel">
      <h3>💡 Light Control Panel</h3>
      <form method="POST" action="/toggle_light">
        <div class="form-group">
          <label>🔑 Enter your NFC UID (without colons):</label>
          <input name="uid" placeholder="e.g. 4625533D" required />
        </div>
        <div class="form-group">
          <label>💡 Select Light Mode:</label>
          <select name="mode">
            <option value="off">🌑 Off</option>
            <option value="low">🌘 Low</option>
            <option value="med">🌗 Medium</option>
            <option value="high">🌕 High</option>
          </select>
        </div>
        <button type="submit">✨ Change Light Mode</button>
      </form>
    </div>

    {% with messages = get_flashed_messages() %}
      {% if messages %}
        {% for m in messages %}
          {% if 'denied' in m.lower() or '❌' in m %}
            <div class="flash error">{{ m }}</div>
          {% else %}
            <div class="flash success">{{ m }}</div>
          {% endif %}
        {% endfor %}
      {% endif %}
    {% endwith %}
    
    <div class="footer">
      <p>🔄 Page auto-refreshes every 30 seconds</p>
      <p>System Time: {{ current_time }}</p>
    </div>
  </div>
</body>
</html>
"""

@app.route("/")
def index():
    last = state["room_control"].get("last_userid") or "None"
    temp = state["room_control"].get("temperature")
    hum = state["room_control"].get("humidity")
    light = state["room_control"].get("light_mode") or "off"
    door_status = state["door_lock"].get("status", "locked")
    
    # Format values
    temp_str = f"{temp:.1f}°C" if temp is not None else "N/A"
    hum_str = f"{hum:.1f}%" if hum is not None else "N/A"
    
    return render_template_string(
        DASH_TEMPLATE, 
        last_user=last, 
        temp=temp_str, 
        hum=hum_str, 
        light=light,
        door_status=door_status,
        allowed_uids=sorted(ALLOWED_UIDS),
        current_time=time.strftime("%Y-%m-%d %H:%M:%S")
    )

@app.route("/toggle_light", methods=["POST"])
def toggle_light():
    uid = (request.form.get("uid") or "").strip().upper()
    mode = request.form.get("mode")
    
    if uid == "":
        flash("❌ UID required.")
        return redirect(url_for("index"))
    
    current_last = state["room_control"].get("last_userid")
    
    if uid != current_last:
        flash(f"❌ Access denied. You ({uid}) are not the current user in the room. Current user: {current_last}")
        return redirect(url_for("index"))
    
    # forward command to light ESP
    cmd = {"device_id":"light", "mode": mode, "requested_by": uid}
    mqtt_client.publish(TOPIC_LIGHT_CMD, json.dumps(cmd))
    flash(f"✅ Light change requested: {mode.upper()}")
    print(f"[WEB] User {uid} requested light mode: {mode}")
    return redirect(url_for("index"))

@app.route("/api/status")
def api_status():
    """API endpoint to get current system status"""
    return {
        "door_lock": state["door_lock"],
        "room_control": state["room_control"],
        "timestamp": int(time.time())
    }

@app.route("/api/send_command", methods=["POST"])
def api_send_command():
    """API endpoint to send commands to ESP32"""
    data = request.get_json()
    command = data.get("command")
    
    if not command:
        return {"status": "error", "message": "Command required"}, 400
    
    cmd = {"command": command, "timestamp": int(time.time())}
    mqtt_client.publish(TOPIC_WEATHER_CONTROL, json.dumps(cmd))
    return {"status": "sent", "command": command}

# -------------------------
# Start services
# -------------------------
if __name__ == "__main__":
    print("\n" + "="*60)
    print("   SMART ROOM MQTT BROKER & WEB DASHBOARD")
    print("="*60)
    print(f"\n[CONFIG] MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"[CONFIG] Firebase: {FIREBASE_URL}")
    print(f"[CONFIG] Allowed UIDs: {len(ALLOWED_UIDS)} cards")
    for uid in sorted(ALLOWED_UIDS):
        print(f"         - {uid}")
    
    print("\n[START] Ensuring Firebase schema...")
    ensure_schema()

    # start mqtt loop thread
    t = threading.Thread(target=mqtt_loop, daemon=True)
    t.start()
    print("\n[START] ✓ MQTT loop started")
    print(f"\n[MQTT] Subscribed topics:")
    print(f"  📥 {TOPIC_NFC_SCAN}")
    print(f"  📥 {TOPIC_WEATHER_SENSOR}")
    print(f"  📥 {TOPIC_WEATHER_STATUS}")
    print(f"  📤 {TOPIC_NFC_RESPONSE}")
    print(f"  📤 {TOPIC_WEATHER_CONTROL}")

    # start flask in main thread
    web_cfg = cfg.get("web", {})
    host = web_cfg.get("host", "0.0.0.0")
    port = int(web_cfg.get("port", 5000))
    
    print(f"\n[WEB] Starting Flask dashboard on http://{host}:{port}")
    print("="*60 + "\n")
    
    app.run(host=host, port=port, debug=False)
