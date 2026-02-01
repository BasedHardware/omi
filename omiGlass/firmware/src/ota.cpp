#include "ota.h"
#include "config.h"

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Update.h>
#include <BLE2902.h>

// OTA State
static uint8_t otaStatus = OTA_STATUS_IDLE;
static uint8_t otaProgress = 0;
static bool otaCancelled = false;

// WiFi credentials (stored temporarily)
static char wifiSSID[WIFI_MAX_SSID_LEN + 1] = {0};
static char wifiPassword[WIFI_MAX_PASS_LEN + 1] = {0};
static bool wifiCredentialsSet = false;

// Firmware URL
static char firmwareURL[OTA_MAX_URL_LEN + 1] = {0};
static bool firmwareURLSet = false;

// OTA task state
static bool otaTaskRunning = false;
static TaskHandle_t otaTaskHandle = NULL;

// BLE Characteristics
static BLECharacteristic *otaControlCharacteristic = NULL;
static BLECharacteristic *otaDataCharacteristic = NULL;

// Forward declarations
static void ota_task(void *parameter);
static bool connect_wifi();
static bool download_and_install_firmware();

// Callback for OTA Control characteristic
class OTAControlCallback : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *pCharacteristic) override {
        std::string value = pCharacteristic->getValue();
        if (value.length() > 0) {
            ota_handle_command((uint8_t *)value.data(), value.length());
        }
    }

    void onRead(BLECharacteristic *pCharacteristic) override {
        // Return current status when read
        uint8_t status[2] = {otaStatus, otaProgress};
        pCharacteristic->setValue(status, 2);
    }
};

void ota_set_characteristics(BLECharacteristic *controlChar, BLECharacteristic *dataChar) {
    otaControlCharacteristic = controlChar;
    otaDataCharacteristic = dataChar;
}

void ota_handle_command(uint8_t *data, size_t length) {
    if (length < 1) return;

    uint8_t command = data[0];
    Serial.printf("OTA: Received command 0x%02X, length %d\n", command, length);

    switch (command) {
        case OTA_CMD_SET_WIFI: {
            // Format: [cmd, ssid_len, ssid..., pass_len, pass...]
            if (length < 3) {
                Serial.println("OTA: Invalid WiFi command length");
                ota_notify_status(OTA_STATUS_ERROR);
                return;
            }

            uint8_t ssidLen = data[1];
            if (ssidLen > WIFI_MAX_SSID_LEN || length < 3 + ssidLen) {
                Serial.println("OTA: Invalid SSID length");
                ota_notify_status(OTA_STATUS_ERROR);
                return;
            }

            memcpy(wifiSSID, &data[2], ssidLen);
            wifiSSID[ssidLen] = '\0';

            uint8_t passLen = data[2 + ssidLen];
            if (passLen > WIFI_MAX_PASS_LEN || length < 3 + ssidLen + passLen) {
                Serial.println("OTA: Invalid password length");
                ota_notify_status(OTA_STATUS_ERROR);
                return;
            }

            memcpy(wifiPassword, &data[3 + ssidLen], passLen);
            wifiPassword[passLen] = '\0';

            wifiCredentialsSet = true;
            Serial.printf("OTA: WiFi credentials set - SSID: %s\n", wifiSSID);
            ota_notify_status(OTA_STATUS_IDLE);
            break;
        }

        case OTA_CMD_SET_URL: {
            // Format: [cmd, url_len (2 bytes big-endian), url...]
            if (length < 4) {
                Serial.println("OTA: Invalid URL command length");
                ota_notify_status(OTA_STATUS_ERROR);
                return;
            }

            uint16_t urlLen = (data[1] << 8) | data[2];
            if (urlLen > OTA_MAX_URL_LEN || length < 3 + urlLen) {
                Serial.println("OTA: Invalid URL length");
                ota_notify_status(OTA_STATUS_ERROR);
                return;
            }

            memcpy(firmwareURL, &data[3], urlLen);
            firmwareURL[urlLen] = '\0';

            firmwareURLSet = true;
            Serial.printf("OTA: Firmware URL set: %s\n", firmwareURL);
            ota_notify_status(OTA_STATUS_IDLE);
            break;
        }

        case OTA_CMD_START_OTA: {
            if (!wifiCredentialsSet) {
                Serial.println("OTA: WiFi credentials not set");
                ota_notify_status(OTA_STATUS_ERROR);
                return;
            }

            if (!firmwareURLSet) {
                Serial.println("OTA: Firmware URL not set");
                ota_notify_status(OTA_STATUS_ERROR);
                return;
            }

            if (otaTaskRunning) {
                Serial.println("OTA: Update already in progress");
                return;
            }

            // Start OTA task
            otaCancelled = false;
            otaTaskRunning = true;
            xTaskCreate(ota_task, "ota_task", 8192, NULL, 5, &otaTaskHandle);
            break;
        }

        case OTA_CMD_CANCEL_OTA: {
            ota_cancel();
            break;
        }

        case OTA_CMD_GET_STATUS: {
            ota_notify_status(otaStatus, otaProgress);
            break;
        }

        default:
            Serial.printf("OTA: Unknown command 0x%02X\n", command);
            ota_notify_status(OTA_STATUS_ERROR);
            break;
    }
}

void ota_notify_status(uint8_t status, uint8_t progress) {
    otaStatus = status;
    otaProgress = progress;

    if (otaDataCharacteristic != NULL) {
        uint8_t notification[2] = {status, progress};
        otaDataCharacteristic->setValue(notification, 2);
        otaDataCharacteristic->notify();
    }

    Serial.printf("OTA: Status 0x%02X, Progress %d%%\n", status, progress);
}

static void ota_task(void *parameter) {
    Serial.println("OTA: Task started");

    // Step 1: Connect to WiFi
    if (!connect_wifi()) {
        ota_notify_status(OTA_STATUS_WIFI_FAILED);
        otaTaskRunning = false;
        vTaskDelete(NULL);
        return;
    }

    if (otaCancelled) {
        WiFi.disconnect(true);
        ota_notify_status(OTA_STATUS_IDLE);
        otaTaskRunning = false;
        vTaskDelete(NULL);
        return;
    }

    // Step 2: Download and install firmware
    if (!download_and_install_firmware()) {
        WiFi.disconnect(true);
        otaTaskRunning = false;
        vTaskDelete(NULL);
        return;
    }

    // Step 3: Reboot
    Serial.println("OTA: Preparing to reboot...");
    ota_notify_status(OTA_STATUS_REBOOTING);
    delay(2000);  // Give time for BLE notification to be sent

    Serial.println("OTA: Disconnecting WiFi...");
    WiFi.disconnect(true);
    WiFi.mode(WIFI_OFF);
    delay(500);

    Serial.println("OTA: Rebooting now!");
    ESP.restart();

    // Should never reach here
    vTaskDelete(NULL);
}

static bool connect_wifi() {
    Serial.printf("OTA: Connecting to WiFi: %s\n", wifiSSID);
    ota_notify_status(OTA_STATUS_WIFI_CONNECTING);

    WiFi.mode(WIFI_STA);
    WiFi.begin(wifiSSID, wifiPassword);

    unsigned long startTime = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (otaCancelled) {
            Serial.println("OTA: WiFi connection cancelled");
            return false;
        }

        if (millis() - startTime > WIFI_CONNECT_TIMEOUT_MS) {
            Serial.println("OTA: WiFi connection timeout");
            return false;
        }

        delay(500);
        Serial.print(".");
    }

    Serial.printf("\nOTA: WiFi connected, IP: %s\n", WiFi.localIP().toString().c_str());
    ota_notify_status(OTA_STATUS_WIFI_CONNECTED);
    return true;
}

static bool download_and_install_firmware() {
    Serial.printf("OTA: Downloading firmware from: %s\n", firmwareURL);
    ota_notify_status(OTA_STATUS_DOWNLOADING, 0);

    // Determine if URL is HTTPS
    bool isHttps = strncmp(firmwareURL, "https://", 8) == 0;
    Serial.printf("OTA: Using %s\n", isHttps ? "HTTPS" : "HTTP");

    WiFiClient *client = nullptr;
    WiFiClientSecure *secureClient = nullptr;

    if (isHttps) {
        secureClient = new WiFiClientSecure;
        if (!secureClient) {
            Serial.println("OTA: Failed to create WiFiClientSecure");
            ota_notify_status(OTA_STATUS_DOWNLOAD_FAILED);
            return false;
        }
        // Skip certificate validation for testing (TODO: add proper certs for production)
        secureClient->setInsecure();
        client = secureClient;
    } else {
        client = new WiFiClient;
        if (!client) {
            Serial.println("OTA: Failed to create WiFiClient");
            ota_notify_status(OTA_STATUS_DOWNLOAD_FAILED);
            return false;
        }
    }

    HTTPClient http;
    http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
    http.begin(*client, firmwareURL);
    http.setTimeout(30000);  // 30 second timeout
    http.addHeader("User-Agent", "ESP32-OTA/1.0");

    Serial.printf("OTA: Starting HTTP GET request...\n");
    int httpCode = http.GET();
    Serial.printf("OTA: HTTP response code: %d\n", httpCode);
    if (httpCode != HTTP_CODE_OK) {
        Serial.printf("OTA: HTTP GET failed, code: %d\n", httpCode);
        ota_notify_status(OTA_STATUS_DOWNLOAD_FAILED);
        http.end();
        if (secureClient) delete secureClient; else delete client;
        return false;
    }

    int contentLength = http.getSize();
    if (contentLength <= 0) {
        Serial.println("OTA: Invalid content length");
        ota_notify_status(OTA_STATUS_DOWNLOAD_FAILED);
        http.end();
        if (secureClient) delete secureClient; else delete client;
        return false;
    }

    Serial.printf("OTA: Firmware size: %d bytes\n", contentLength);

    // Check if there's enough space
    if (!Update.begin(contentLength)) {
        Serial.println("OTA: Not enough space for update");
        ota_notify_status(OTA_STATUS_INSTALL_FAILED);
        http.end();
        if (secureClient) delete secureClient; else delete client;
        return false;
    }

    WiFiClient *stream = http.getStreamPtr();
    uint8_t buffer[1024];
    int totalRead = 0;
    int lastProgress = -1;

    ota_notify_status(OTA_STATUS_INSTALLING, 0);

    while (http.connected() && totalRead < contentLength) {
        if (otaCancelled) {
            Serial.println("OTA: Download cancelled");
            Update.abort();
            http.end();
            if (secureClient) delete secureClient; else delete client;
            ota_notify_status(OTA_STATUS_IDLE);
            return false;
        }

        size_t available = stream->available();
        if (available > 0) {
            size_t toRead = min(available, sizeof(buffer));
            int bytesRead = stream->readBytes(buffer, toRead);

            if (bytesRead > 0) {
                if (Update.write(buffer, bytesRead) != bytesRead) {
                    Serial.println("OTA: Write failed");
                    Update.abort();
                    http.end();
                    if (secureClient) delete secureClient; else delete client;
                    ota_notify_status(OTA_STATUS_INSTALL_FAILED);
                    return false;
                }

                totalRead += bytesRead;
                int progress = (totalRead * 100) / contentLength;

                // Notify progress every 5%
                if (progress != lastProgress && progress % 5 == 0) {
                    ota_notify_status(OTA_STATUS_INSTALLING, progress);
                    lastProgress = progress;
                }
            }
        } else {
            delay(10);
        }
    }

    http.end();

    // Properly delete the client based on type
    if (secureClient) {
        delete secureClient;
    } else {
        delete client;
    }

    if (totalRead != contentLength) {
        Serial.printf("OTA: Incomplete download: %d/%d\n", totalRead, contentLength);
        Update.abort();
        ota_notify_status(OTA_STATUS_DOWNLOAD_FAILED);
        return false;
    }

    if (!Update.end(true)) {
        Serial.printf("OTA: Update failed: %s\n", Update.errorString());
        ota_notify_status(OTA_STATUS_INSTALL_FAILED);
        return false;
    }

    Serial.println("OTA: Update complete!");
    ota_notify_status(OTA_STATUS_INSTALL_COMPLETE, 100);
    delay(500);  // Give BLE time to send notification
    return true;
}

void ota_loop() {
    // Currently nothing needed in loop - OTA runs in separate task
}

uint8_t ota_get_status() {
    return otaStatus;
}

bool ota_is_busy() {
    return otaTaskRunning;
}

void ota_cancel() {
    if (otaTaskRunning) {
        Serial.println("OTA: Cancelling...");
        otaCancelled = true;
    }
}
