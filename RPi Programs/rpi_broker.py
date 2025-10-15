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

# Topics
TOPIC_DOOR_REQ = "esp/door_lock/request"
TOPIC_DOOR_RESP = "esp/door_lock/response"
TOPIC_ROOM_SENSOR = "esp/room/sensor"
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
    client.subscribe([(TOPIC_DOOR_REQ, 0), (TOPIC_ROOM_SENSOR, 0), (TOPIC_LIGHT_STATUS, 0)])
    print("[MQTT] Subscribed to topics.")

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        topic = msg.topic
        print(f"[MQTT] {topic} -> {payload}")
        data = json.loads(payload)
    except Exception as e:
        print("[MQTT] Bad message:", e)
        return

    if topic == TOPIC_DOOR_REQ:
        handle_door_request(data)
    elif topic == TOPIC_ROOM_SENSOR:
        handle_room_sensor(data)
    elif topic == TOPIC_LIGHT_STATUS:
        handle_light_status(data)

def handle_door_request(data):
    """
    expected data:
    {
      "device_id":"door_lock",
      "nfc_uid":"A1B2C3D4",
      "action":"unlock_request"
    }
    """
    uid = str(data.get("nfc_uid","")).upper()
    device_id = data.get("device_id","door_lock")
    action = data.get("action","unlock_request")

    if uid == "":
        print("[DOOR] Empty UID")
        return

    now = int(time.time())

    # Check allowed_uids
    approved = uid in ALLOWED_UIDS
    if approved:
        print(f"[ACCESS] UID {uid} authorized. Granting access.")
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

        # send grant response to door ESP so it actuates
        resp = {"access":"granted", "nfc_uid": uid}
        mqtt_client.publish(TOPIC_DOOR_RESP, json.dumps(resp))
    else:
        print(f"[ACCESS] UID {uid} denied.")
        # send deny
        resp = {"access":"denied", "nfc_uid": uid}
        mqtt_client.publish(TOPIC_DOOR_RESP, json.dumps(resp))
        # log to firebase
        fb_patch("/devices/door_lock", {
            "last_attempt": uid,
            "last_attempt_at": now
        })

def handle_room_sensor(data):
    """
    expected:
    {
      "device_id":"room_control",
      "temperature": 26.5,
      "humidity": 58.2
    }
    """
    temp = data.get("temperature")
    hum = data.get("humidity")
    now = int(time.time())
    if temp is not None or hum is not None:
        state["room_control"]["temperature"] = temp
        state["room_control"]["humidity"] = hum
        state["room_control"]["updated_at"] = now
        # update firebase device node
        fb_patch("/devices/room_control", {
            "temperature": temp,
            "humidity": hum,
            "updated_at": now
        })
        print(f"[SENSOR] Updated room sensor {temp}C {hum}%")

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
        print(f"[LIGHT] mode updated: {mode}")

# -------------------------
# MQTT client setup
# -------------------------
mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

def mqtt_loop():
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_forever()

# -------------------------
# Flask web app (simple)
# -------------------------
app = Flask(__name__)
app.secret_key = "replace_with_a_random_string_for_prod"

DASH_TEMPLATE = """
<!doctype html>
<title>Room Dashboard</title>
<h2>Room Dashboard</h2>
<p>Last user in room: <strong>{{ last_user }}</strong></p>
<p>Temperature: {{ temp }} °C</p>
<p>Humidity: {{ hum }} %</p>
<p>Light mode: {{ light }}</p>

<form method="POST" action="/toggle_light">
  <label>Enter your UID (HEX, no colons): <input name="uid" /></label>
  <select name="mode">
    <option value="off">Off</option>
    <option value="low">Low</option>
    <option value="med">Medium</option>
    <option value="high">High</option>
  </select>
  <button type="submit">Request Light Change</button>
</form>

{% with messages = get_flashed_messages() %}
  {% if messages %}
    <ul>
      {% for m in messages %}
        <li>{{ m }}</li>
      {% endfor %}
    </ul>
  {% endif %}
{% endwith %}
"""

@app.route("/")
def index():
    last = state["room_control"].get("last_userid") or "None"
    temp = state["room_control"].get("temperature") or "N/A"
    hum = state["room_control"].get("humidity") or "N/A"
    light = state["room_control"].get("light_mode") or "off"
    return render_template_string(DASH_TEMPLATE, last_user=last, temp=temp, hum=hum, light=light)

@app.route("/toggle_light", methods=["POST"])
def toggle_light():
    uid = (request.form.get("uid") or "").strip().upper()
    mode = request.form.get("mode")
    if uid == "":
        flash("UID required.")
        return redirect(url_for("index"))
    current_last = state["room_control"].get("last_userid")
    if uid != current_last:
        flash("Access denied. You are not the current user in the room.")
        return redirect(url_for("index"))
    # forward command to light ESP
    cmd = {"device_id":"light", "mode": mode, "requested_by": uid}
    mqtt_client.publish(TOPIC_LIGHT_CMD, json.dumps(cmd))
    flash(f"Light change requested: {mode}")
    return redirect(url_for("index"))

# -------------------------
# Start services
# -------------------------
if __name__ == "__main__":
    print("[START] Ensuring Firebase schema...")
    ensure_schema()

    # start mqtt loop thread
    t = threading.Thread(target=mqtt_loop, daemon=True)
    t.start()
    print("[START] MQTT loop started.")

    # start flask in main thread
    web_cfg = cfg.get("web", {})
    host = web_cfg.get("host", "0.0.0.0")
    port = int(web_cfg.get("port", 5000))
    print(f"[WEB] Starting Flask on {host}:{port}")
    app.run(host=host, port=port)
