// esp32_room_sensor.ino
// Libraries: DHT sensor library, WiFi, PubSubClient

#include <WiFi.h>
#include <PubSubClient.h>
#include "DHT.h"

const char* ssid = "YOUR_SSID";
const char* password = "YOUR_WIFI_PASS";
const char* mqtt_server = "192.168.254.111";

#define DHTPIN 4     // connect DHT data pin
#define DHTTYPE DHT22

DHT dht(DHTPIN, DHTTYPE);
WiFiClient espClient;
PubSubClient client(espClient);

const char* TOPIC_SENSOR = "esp/room/sensor";
String device_id = "room_control";

void setup_wifi() {
  WiFi.begin(ssid, password);
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(300); Serial.print("."); }
  Serial.println("WiFi connected");
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Attempting MQTT...");
    if (client.connect("esp32_room")) {
      Serial.println("connected");
    } else {
      Serial.print("failed rc=");
      Serial.print(client.state());
      Serial.println(" try again in 2s");
      delay(2000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  dht.begin();
  setup_wifi();
  client.setServer(mqtt_server, 1883);
}

void loop() {
  if (!client.connected()) reconnect();
  client.loop();

  float h = dht.readHumidity();
  float t = dht.readTemperature();
  if (isnan(t) || isnan(h)) {
    Serial.println("Failed to read DHT");
  } else {
    // publish JSON
    String payload = "{\"device_id\":\"" + device_id + "\",\"temperature\":" + String(t,1) + ",\"humidity\":" + String(h,1) + "}";
    client.publish(TOPIC_SENSOR, payload.c_str());
    Serial.println("Published sensor: " + payload);
  }
  delay(10000); // sample every 10s (adjust)
}
