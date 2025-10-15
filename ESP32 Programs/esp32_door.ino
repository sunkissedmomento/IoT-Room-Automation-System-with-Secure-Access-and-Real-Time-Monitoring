// esp32_door.ino
// Libraries required:
// - Adafruit PN532
// - U8g2 (for display) optional
// - WiFi
// - PubSubClient
// - Servo

#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Adafruit_PN532.h>
#include <Servo.h>
#include <U8g2lib.h>

// ========== WiFi / MQTT ==========
const char* ssid = "YOUR_SSID";
const char* password = "YOUR_WIFI_PASS";
const char* mqtt_server = "192.168.254.111"; // set to your broker IP
WiFiClient espClient;
PubSubClient client(espClient);

// ========== PN532 I2C ==========
#define SDA_PIN 21
#define SCL_PIN 22
Adafruit_PN532 nfc(SDA_PIN, SCL_PIN);

// ========== Display (optional) ==========
U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0);

// ========== Servo ==========
#define SERVO_PIN 23
Servo doorServo;

// ========== Topics ==========
const char* TOPIC_REQ = "esp/door_lock/request";
const char* TOPIC_RESP = "esp/door_lock/response";

String device_id = "door_lock";

void displayText(const char* t) {
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_ncenB08_tr);
  u8g2.drawStr(0, 24, t);
  u8g2.sendBuffer();
}

void callback(char* topic, byte* payload, unsigned int length) {
  String msg = "";
  for (unsigned int i=0;i<length;i++) msg += (char)payload[i];
  Serial.print("Received on ["); Serial.print(topic); Serial.print("]: "); Serial.println(msg);

  // parse simple JSON-ish manually or use ArduinoJson if preferred
  if (String(topic) == TOPIC_RESP) {
    if (msg.indexOf("\"granted\"") >= 0) {
      displayText("Access Granted");
      // unlock servo briefly
      doorServo.write(90);
      delay(3000);
      doorServo.write(0);
      displayText("Locked");
    } else {
      displayText("Access Denied");
      delay(1500);
      displayText("Scan Card");
    }
  }
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    if (client.connect("esp32_door")) {
      Serial.println("connected");
      client.subscribe(TOPIC_RESP);
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 2s");
      delay(2000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  Wire.begin(SDA_PIN, SCL_PIN);
  u8g2.begin();
  displayText("Init NFC...");
  delay(500);

  doorServo.attach(SERVO_PIN);
  doorServo.write(0); // locked position

  // NFC
  nfc.begin();
  uint32_t ver = nfc.getFirmwareVersion();
  if (!ver) {
    displayText("PN532 not found");
    while (1) delay(10);
  }
  nfc.SAMConfig();
  displayText("Scan Card");

  // WiFi
  WiFi.begin(ssid, password);
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }
  Serial.println("WiFi connected");
  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);
}

void loop() {
  if (!client.connected()) reconnect();
  client.loop();

  boolean success;
  uint8_t uid[7];
  uint8_t uidLength;
  success = nfc.readPassiveTargetID(PN532_MIFARE_ISO14443A, uid, &uidLength, 1000);
  if (success) {
    // build UID hex string (no colons)
    String uidhex = "";
    for (uint8_t i = 0; i < uidLength; i++) {
      if (uid[i] < 0x10) uidhex += "0";
      uidhex += String(uid[i], HEX);
    }
    uidhex.toUpperCase();
    Serial.print("UID: "); Serial.println(uidhex);
    displayText("Card read...");

    // build simple JSON
    String payload = "{\"device_id\":\"" + device_id + "\",\"nfc_uid\":\"" + uidhex + "\",\"action\":\"unlock_request\"}";
    client.publish(TOPIC_REQ, payload.c_str());
    // wait for response via callback (door will actuate when response arrives)
    // add a short debounce
    delay(2000);
    displayText("Scan Card");
  }

  delay(200);
}
