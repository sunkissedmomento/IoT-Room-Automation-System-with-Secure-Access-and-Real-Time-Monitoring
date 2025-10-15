# IoT Room Automation System with Secure Access and Real-Time Monitoring

**Proposed by:**  
**Marc Anthony M. San Juan**  
BS Computer Engineering Student

---

## 🧠 1. Introduction

This project implements an **IoT-based Room Automation System** integrating door access, temperature monitoring, and lighting control using **ESP32 microcontrollers**, a **Raspberry Pi 5** (as MQTT broker), and **Firebase Realtime Database** for cloud synchronization.

The system focuses on **security**, **automation**, and **real-time monitoring**, ensuring that only authorized users can access and control the environment.

---

## 🎯 2. Objectives

### General Objective
Develop a secure and automated IoT-based room system using ESP32 devices, Raspberry Pi, and Firebase.

### Specific Objectives
- Implement **NFC-based authentication** for door access.
- Collect and monitor **temperature and humidity** data in real time.
- Control **lighting levels** through both hardware buttons and a web dashboard.
- Use **Raspberry Pi 5** as a local MQTT broker and Firebase synchronizer.
- Provide a **web dashboard** for remote monitoring and control.

---

## 🧩 3. System Overview

| Device               | Function                       | Description                              |
|----------------------|-------------------------------|------------------------------------------|
| **ESP32 #1**         | Door Lock Controller           | Manages door solenoid lock via NFC authentication. |
| **ESP32 #2**         | Temp & Humidity Sensor         | Sends DHT22/BME280 data to MQTT for cloud sync. |
| **ESP32 #3**         | Light Controller               | Controls room lighting modes (Low, Medium, High). |
| **Raspberry Pi 5**   | MQTT Broker + Firebase Bridge  | Hosts Mosquitto broker & Python sync service. |
| **Web App (Flask)**  | Dashboard                      | Displays Firebase data, allows user control.      |

---

## 🔗 4. System Architecture

1. User taps NFC → ESP32 verifies UID via Firebase `allowed_uids`.
2. If authorized → Door unlocks and logs `last_user` in Firebase.
3. Temperature & humidity sensor updates data to MQTT → Firebase.
4. Light control adjusts via web or physical buttons.
5. Raspberry Pi handles synchronization between MQTT and Firebase.

---

## 🧱 5. Firebase RTDB Structure
```
{
"devices": {
"door_lock": {
"device_id": "DL001",
"status": "locked",
"last_user": "A1B2C3D4"
},
"temperature_sensor": {
"device_id": "TMP001",
"temperature": 26.5,
"humidity": 59.3,
"last_user": "A1B2C3D4"
},
"light_control": {
"device_id": "LC001",
"status": "medium",
"last_user": "A1B2C3D4"
}
},
"allowed_uids": ["4625533D", "A1B2C3D4", "999888777"]
}
```

---

## ⚙️ 6. Components Needed

### Hardware
- 3 × ESP32 Development Boards
- 1 × Raspberry Pi 5
- 1 × PN532 NFC Reader (I2C or SPI)
- 1 × DHT22 or BME280 Sensor
- 1 × 3-Channel Relay or MOSFET Driver
- 1 × Solenoid Door Lock (12V)
- 1 × TIP120 or MOSFET for lock control
- 1 × 12V Power Supply
- Jumper Wires, Breadboard, Resistors

### Software
- Arduino IDE
- Python 3
- Mosquitto MQTT Broker
- Firebase Realtime Database
- Flask (for web dashboard)

---

## 🪜 7. Setup Guide

### A. Setting Up Firebase

1. Go to the [Firebase Console](https://console.firebase.google.com/)
2. Create a new project and enable Realtime Database.
3. Go to *Project Settings* → *Service Accounts* → *Generate New Private Key*.
4. Save it as `firebase_key.json` in your Raspberry Pi project folder.
5. Copy your Database URL (e.g., `https://your-project.firebaseio.com/`).

### B. Raspberry Pi 5 Setup (Broker + Sync)

**Update and install dependencies:**
sudo apt update && sudo apt upgrade -y
sudo apt install mosquitto mosquitto-clients python3-pip -y
pip3 install paho-mqtt firebase-admin flask

```

**Enable Mosquitto:**
sudo systemctl enable mosquitto
sudo systemctl start mosquitto

```

**Create `config.json`:**
```
{
"firebase": {
"api_key": "YOUR_FIREBASE_API_KEY",
"database_url": "https://your-project.firebaseio.com/"
},
"mqtt": {
"broker_ip": "192.168.254.111",
"port": 1883
},
"devices": ["door_lock", "temperature_sensor", "light_control"],
"allowed_uids": ["4625533D", "A1B2C3D4", "999888777"]
}
```

**Example Python bridge (`rpi_bridge.py`):**
```
import json, time, paho.mqtt.client as mqtt
import firebase_admin
from firebase_admin import credentials, db

with open('config.json') as f:
config = json.load(f)

cred = credentials.Certificate("firebase_key.json")
firebase_admin.initialize_app(cred, {
"databaseURL": config["firebase"]["database_url"]
})

broker_ip = config["mqtt"]["broker_ip"]
port = config["mqtt"]["port"]

def on_message(client, userdata, msg):
topic = msg.topic
payload = msg.payload.decode()
print(f"Received {payload} on {topic}")
db.reference(f"/devices/{topic}").set(json.loads(payload))

client = mqtt.Client()
client.on_message = on_message
client.connect(broker_ip, port)
client.subscribe("door_lock")
client.subscribe("temperature_sensor")
client.subscribe("light_control")

print("MQTT-Firebase Bridge Running...")
client.loop_forever()
```

### C. ESP32 Setup

1. **Install Board Support**  
   - File → Preferences → *Additional Boards Manager URLs*:  
     `https://dl.espressif.com/dl/package_esp32_index.json`
   - Tools → Board → ESP32 → Install ESP32 core

2. **Install Libraries**  
   - WiFi.h  
   - PubSubClient.h  
   - Adafruit_PN532.h  
   - DHT.h or Adafruit_BME280.h  

3. **Flash Each ESP32 Example (Door Lock):**
```
#include <WiFi.h>
#include <PubSubClient.h>
#include <Adafruit_PN532.h>

const char* ssid = "YOUR_WIFI";
const char* password = "YOUR_PASS";
const char* mqtt_server = "192.168.254.111";

WiFiClient espClient;
PubSubClient client(espClient);

void setup() {
Serial.begin(115200);
WiFi.begin(ssid, password);
while (WiFi.status() != WL_CONNECTED) delay(500);
client.setServer(mqtt_server, 1883);
client.connect("door_lock");
Serial.println("Door Lock ready");
}

void loop() {
if (!client.connected()) client.connect("door_lock");
client.loop();
// NFC read logic here → publish to MQTT if valid UID
}

```
*(Repeat similarly for `temperature_sensor.ino` and `light_control.ino`)*

### D. Flask Web Dashboard (optional)

A minimal dashboard to view and control devices:
```
from flask import Flask, render_template_string
import firebase_admin
from firebase_admin import credentials, db

cred = credentials.Certificate("firebase_key.json")
firebase_admin.initialize_app(cred, {"databaseURL": "https://your-project.firebaseio.com/"})

app = Flask(name)

@app.route('/')
def dashboard():
ref = db.reference("/devices")
data = ref.get()
return render_template_string("""
<h2>IoT Room Dashboard</h2>
<pre>{{ data }}</pre>
""", data=data)

if name == 'main':
app.run(host='0.0.0.0', port=5000)
```

---

## 🧠 8. Expected Features

- ✅ Secure NFC-based door access
- ✅ Real-time sensor monitoring via Firebase
- ✅ Web dashboard for remote viewing/control
- ✅ Modular MQTT architecture for scalability

---

## 🧩 9. Future Enhancements

- Multi-room expansion
- Voice assistant control
- Motion-based automation

---

## 👨‍💻 Author

**Marc Anthony M. San Juan**  
BS Computer Engineering Student  

---

## 🪪 License

This project is open-source for educational purposes.  
Feel free to modify and improve upon it.
