// esp32_light.ino
#include <WiFi.h>
#include <PubSubClient.h>

const char* ssid = "YOUR_SSID";
const char* password = "YOUR_WIFI_PASS";
const char* mqtt_server = "192.168.254.111";

WiFiClient espClient;
PubSubClient client(espClient);

const char* TOPIC_CMD = "esp/light/cmd";
const char* TOPIC_STATUS = "esp/light/status";

String device_id = "light";
String current_mode = "off";

// define your output pins for lights (could be PWM pins)
#define PIN_LOW 14
#define PIN_MED 12
#define PIN_HIGH 13

void apply_mode(const String &mode) {
  if (mode == "off") {
    digitalWrite(PIN_LOW, LOW);
    digitalWrite(PIN_MED, LOW);
    digitalWrite(PIN_HIGH, LOW);
  } else if (mode == "low") {
    digitalWrite(PIN_LOW, HIGH);
    digitalWrite(PIN_MED, LOW);
    digitalWrite(PIN_HIGH, LOW);
  } else if (mode == "med") {
    digitalWrite(PIN_LOW, LOW);
    digitalWrite(PIN_MED, HIGH);
    digitalWrite(PIN_HIGH, LOW);
  } else if (mode == "high") {
    digitalWrite(PIN_LOW, LOW);
    digitalWrite(PIN_MED, LOW);
    digitalWrite(PIN_HIGH, HIGH);
  }
}

void callback(char* topic, byte* payload, unsigned int length) {
  String msg = "";
  for (unsigned int i = 0; i < length; i++) msg += (char)payload[i];
  Serial.println("Msg: " + msg);

  // parse simple for "mode":"..."
  int idx = msg.indexOf("\"mode\"");
  if (idx >= 0) {
    int colon = msg.indexOf(":", idx);
    int quote1 = msg.indexOf("\"", colon);
    int quote2 = msg.indexOf("\"", quote1 + 1);
    String mode = msg.substring(quote1 + 1, quote2);
    mode.toLowerCase();
    current_mode = mode;
    apply_mode(mode);

    // publish status
    String status = "{\"device_id\":\"light\",\"mode\":\"" + current_mode + "\"}";
    client.publish(TOPIC_STATUS, status.c_str());
  }
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("MQTT connecting...");
    if (client.connect("esp32_light")) {
      Serial.println("connected");
      client.subscribe(TOPIC_CMD);
      // publish initial status
      String status = "{\"device_id\":\"light\",\"mode\":\"" + current_mode + "\"}";
      client.publish(TOPIC_STATUS, status.c_str());
    } else {
      Serial.print("fail rc=");
      Serial.print(client.state());
      Serial.println(" try in 2s");
      delay(2000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_LOW, OUTPUT);
  pinMode(PIN_MED, OUTPUT);
  pinMode(PIN_HIGH, OUTPUT);
  apply_mode("off");

  WiFi.begin(ssid, password);
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(300); Serial.print("."); }
  Serial.println("WiFi connected");

  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);
}

void loop() {
  if (!client.connected()) reconnect();
  client.loop();
  // nothing else needed; actions come from MQTT
  delay(100);
}
