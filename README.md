# IoT Room Automation System with Secure Access and Real-Time Monitoring

**Proposed by:**  
Marc Anthony M. San Juan  
**BS Computer Engineering Student**

---

## 1. Introduction

This project proposes the development of an **IoT-based Room Automation System** that integrates door access control, temperature monitoring, and lighting management using **ESP32 microcontrollers**, a **Raspberry Pi 5 broker**, and **Firebase Realtime Database** for cloud synchronization.

The system aims to automate and secure room operations by linking devices through an **MQTT communication protocol** while maintaining centralized data management in Firebase. Only authorized users can access and control the system based on their registered credentials.

---

## 2. Objectives

### General Objective
To design and implement an IoT-powered room system that enhances automation, security, and user control through real-time monitoring and authenticated access.

### Specific Objectives
- Develop a door lock system that verifies users through an NFC tag before granting access.  
- Monitor room temperature and humidity and send real-time data to Firebase.  
- Implement a light control system with three operating modes (Low, Medium, High).  
- Use a Raspberry Pi 5 as a central MQTT broker to collect and synchronize data to Firebase RTDB.  
- Build a simple web dashboard to display device statuses and allow control by authorized users.

---

## 3. System Overview

The project consists of **three ESP32 devices** and **one Raspberry Pi 5** acting as a local broker and cloud bridge.

| Component | Function | Description |
|------------|-----------|-------------|
| ESP32 #1 | Door Lock Controller | Controls solenoid lock; verifies NFC tag UID; logs last user who accessed the room. |
| ESP32 #2 | Temperature & Humidity Sensor | Collects and transmits environmental data (DHT22 or BME280) to MQTT. |
| ESP32 #3 | Light Control Module | Manages lighting modes via relay or MOSFET driver and records the last user who changed the state. |
| Raspberry Pi 5 | MQTT Broker & Firebase Sync | Acts as a local Mosquitto broker; synchronizes MQTT topics to Firebase RTDB; reads configuration from a JSON file. |
| Web App (Flask) | Monitoring & Control Interface | Displays data from Firebase and allows remote control of devices through a web GUI. |

---

## 4. System Architecture

### Flow of Operation
1. User taps NFC card → ESP32 Door Lock validates UID from Firebase `allowed_uids`.  
2. If valid, the door unlocks and updates Firebase with user ID and access time.  
3. The temperature sensor continuously sends temperature and humidity data to MQTT.  
4. The light controller adjusts brightness through local buttons or web commands.  
5. Raspberry Pi 5 listens to all MQTT topics (`door_lock`, `temp_sensor`, `light_control`), updates Firebase in real time, and reads configurations from a `config.json` file.

---

## 5. Firebase RTDB Schema
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
      "temperature": 25.8,
      "humidity": 60.5,
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
text

---

## 6. Components Needed

### Hardware
- 3 × ESP32 Development Boards  
- 1 × Raspberry Pi 5 (or Raspberry Pi 4)  
- 1 × PN532 NFC Module (for Door Lock ESP32)  
- 1 × DHT22 or BME280 Temperature & Humidity Sensor  
- 1 × 3-Channel Relay Module (for Light Control)  
- 1 × Solenoid Door Lock + Power Driver (e.g., TIP120)  
- 1 × Breadboard & Jumper Wires  
- 1 × 12V Power Supply  

### Software
- Python 3 (for Raspberry Pi)  
- Mosquitto MQTT Broker  
- Firebase Realtime Database  
- Arduino IDE (for ESP32 firmware)  
- Flask (for Web App Interface)  
- `config.json` (for API key and broker configuration)

---

## 7. Expected Features

- ✅ Secure NFC-based room access  
- ✅ Real-time monitoring (temperature, humidity, light mode)  
- ✅ Automatic synchronization with Firebase  
- ✅ Simple and responsive web dashboard  
- ✅ Modular and scalable MQTT-based communication  

---

## 8. Expected Output

- A fully functional IoT room system with three interconnected ESP32 boards and one Raspberry Pi broker.  
- Real-time device data displayed on Firebase and a local web dashboard.  
- Secure access control ensuring only authorized users can interact with devices.

---

## 9. Conclusion

The proposed system demonstrates the integration of IoT and cloud computing for efficient, secure, and real-time room management.  
By combining **ESP32 nodes**, a **Raspberry Pi broker**, and **Firebase cloud services**, this project provides a smart, scalable, and educational platform for automation and control systems.

---

## 10. Future Enhancements

- Integration with voice assistants (Google Assistant / Alexa)  
- Addition of motion detection and energy-saving modes  
- Expansion for multi-room or multi-user management  

---

## Author

**Marc Anthony M. San Juan**  
BS Computer Engineering Student 
