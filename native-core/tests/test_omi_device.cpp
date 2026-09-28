// Host test suite for the portable BLE device library (omi_device).
// Framework-free, mirroring the assertion style of the other native-core
// suites; the cases port OmiKit's DevicesTests so Apple and C++ suites share
// semantics.
#include "omi_device.h"
#include "omi_native_boundary.h"

#include <cstring>
#include <cstdio>
#include <string>
#include <vector>

static int failures = 0;

#define CHECK(condition, message)                                              \
    do {                                                                       \
        if (!(condition)) {                                                    \
            failures++;                                                        \
            std::printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, message);      \
        }                                                                      \
    } while (0)

#define CHECK_EQ_INT(actual, expected, message)                                \
    do {                                                                       \
        const long long a = (long long)(actual);                               \
        const long long e = (long long)(expected);                             \
        if (a != e) {                                                          \
            failures++;                                                        \
            std::printf("FAIL %s:%d  %s (actual %lld, expected %lld)\n",       \
                        __FILE__, __LINE__, message, a, e);                    \
        }                                                                      \
    } while (0)

#define CHECK_EQ_STR(actual, expected, message)                                \
    do {                                                                       \
        const std::string a = (actual);                                        \
        const std::string e = (expected);                                      \
        if (a != e) {                                                          \
            failures++;                                                        \
            std::printf("FAIL %s:%d  %s (actual \"%s\", expected \"%s\")\n",   \
                        __FILE__, __LINE__, message, a.c_str(), e.c_str());    \
        }                                                                      \
    } while (0)

// Builds a real 0xAA 0x55 framed body: sync bytes + payload + CRC32 big
// endian, computed by the middleware itself.
static std::vector<uint8_t> framed_body(const std::vector<uint8_t>& payload) {
    const uint32_t crc = omi_calculate_packet_checksum(
        payload.data(), payload.size());
    std::vector<uint8_t> body;
    body.push_back(0xAA);
    body.push_back(0x55);
    body.insert(body.end(), payload.begin(), payload.end());
    body.push_back((uint8_t)((crc >> 24) & 0xFF));
    body.push_back((uint8_t)((crc >> 16) & 0xFF));
    body.push_back((uint8_t)((crc >> 8) & 0xFF));
    body.push_back((uint8_t)(crc & 0xFF));
    return body;
}

static std::vector<uint8_t> raw_packet(uint16_t index,
                                       const std::vector<uint8_t>& payload) {
    std::vector<uint8_t> raw;
    raw.push_back((uint8_t)(index & 0xFF));
    raw.push_back((uint8_t)(index >> 8));
    const std::vector<uint8_t> body = framed_body(payload);
    raw.insert(raw.end(), body.begin(), body.end());
    return raw;
}

static void test_note_pin_advertisement() {
    const uint8_t note_pin[] = {93, 0x00, 0x04, 0x56, 0xCF, 0x00};
    CHECK_EQ_INT(omi_device_is_note_pin_advertisement(note_pin, sizeof(note_pin)), 1, "NotePin payload matches");
    const uint8_t wrong_payload[] = {93, 0x00, 0x04, 0x56, 0x00, 0x00};
    CHECK_EQ_INT(omi_device_is_note_pin_advertisement(wrong_payload, sizeof(wrong_payload)), 0, "wrong payload rejected");
    CHECK_EQ_INT(omi_device_is_note_pin_advertisement(nullptr, 0), 0, "absent data rejected");
    const uint8_t short_data[] = {93, 0x00};
    CHECK_EQ_INT(omi_device_is_note_pin_advertisement(short_data, sizeof(short_data)), 0, "short data rejected");
    const uint8_t other_vendor[] = {0x4C, 0x00, 0x04, 0x56, 0xCF, 0x00};
    CHECK_EQ_INT(omi_device_is_note_pin_advertisement(other_vendor, sizeof(other_vendor)), 0, "other vendor id rejected");
}

static void test_discovered_name() {
    char out[128];
    CHECK_EQ_INT(omi_device_discovered_name("Omi", "Stale", nullptr, 0, out, sizeof(out)), 3, "advertised preferred");
    CHECK_EQ_STR(out, "Omi", "advertised value");
    CHECK_EQ_INT(omi_device_discovered_name(nullptr, "Omi", nullptr, 0, out, sizeof(out)), 3, "cached fallback");
    CHECK_EQ_STR(out, "Omi", "cached value");
    CHECK_EQ_INT(omi_device_discovered_name("  ", nullptr, nullptr, 0, out, sizeof(out)), 0, "blank resolves empty");
    CHECK_EQ_STR(out, "", "blank value");
    const uint8_t note_pin[] = {93, 0x00, 0x04, 0x56, 0xCF, 0x00};
    CHECK_EQ_INT(omi_device_discovered_name(nullptr, nullptr, note_pin, sizeof(note_pin), out, sizeof(out)), 7, "NotePin fallback");
    CHECK_EQ_STR(out, "NotePin", "NotePin value");
    CHECK_EQ_INT(omi_device_discovered_name(nullptr, nullptr, nullptr, 0, out, sizeof(out)), 0, "nothing resolves empty");
    // Trimming removes surrounding ASCII whitespace only.
    CHECK_EQ_INT(omi_device_discovered_name(" Omi \n", nullptr, nullptr, 0, out, sizeof(out)), 3, "trimmed advertised");
    CHECK_EQ_STR(out, "Omi", "trimmed value");
}

static void test_omi_like_filter() {
    CHECK_EQ_INT(omi_device_is_omi_like("Omi"), 1, "Omi is omi-like");
    CHECK_EQ_INT(omi_device_is_omi_like("NotePin"), 1, "NotePin is omi-like");
    CHECK_EQ_INT(omi_device_is_omi_like("notepin s"), 1, "lowercase notepin matches");
    CHECK_EQ_INT(omi_device_is_omi_like("JBL Flip"), 0, "unrelated name rejected");
    CHECK_EQ_INT(omi_device_is_omi_like(nullptr), 0, "absent name rejected");
}

static void test_battery_persistence_rule() {
    CHECK_EQ_INT(omi_device_should_persist_battery_reading(0, 0, 0, 0, 80, 0), 1, "first reading persists");
    CHECK_EQ_INT(omi_device_should_persist_battery_reading(80, 1, 0, 1, 80, 1000), 0, "unchanged reading within hour suppressed");
    CHECK_EQ_INT(omi_device_should_persist_battery_reading(80, 1, 0, 1, 79, 1000), 1, "level change persists");
    CHECK_EQ_INT(omi_device_should_persist_battery_reading(
                     80, 1, 0, 1, 80, OMI_DEVICE_BATTERY_HISTORY_MIN_INTERVAL_MS),
                 1, "hour boundary persists");
}

static void test_characteristic_text() {
    char out[256];

    const uint8_t model[] = {'O', 'm', 'i', ' ', 'D', 'e', 'v', 'i', 'c', 'e'};
    CHECK_EQ_INT(omi_device_characteristic_text(model, sizeof(model), out, sizeof(out)), 10, "valid text kept");
    CHECK_EQ_STR(out, "Omi Device", "valid text value");

    const uint8_t padded[] = {' ', '\t', 'v', '1', '.', '2', '\n'};
    CHECK_EQ_INT(omi_device_characteristic_text(padded, sizeof(padded), out, sizeof(out)), 4, "whitespace trimmed");
    CHECK_EQ_STR(out, "v1.2", "trimmed value");

    // UTF-8 multibyte content ("Café") round-trips.
    const uint8_t utf8[] = {'C', 'a', 'f', 0xC3, 0xA9};
    CHECK_EQ_INT(omi_device_characteristic_text(utf8, sizeof(utf8), out, sizeof(out)), 5, "utf8 kept");
    CHECK_EQ_STR(out, "Caf\xC3\xA9", "utf8 value");

    CHECK(omi_device_characteristic_text(nullptr, 0, out, sizeof(out)) < 0, "absent rejected");
    const uint8_t blank[] = {' ', ' '};
    CHECK(omi_device_characteristic_text(blank, sizeof(blank), out, sizeof(out)) < 0, "blank rejected");
    const uint8_t with_nul[] = {'v', '1', 0x00};
    CHECK(omi_device_characteristic_text(with_nul, sizeof(with_nul), out, sizeof(out)) < 0, "NUL padding rejected");
    const uint8_t with_control[] = {'v', 0x01};
    CHECK(omi_device_characteristic_text(with_control, sizeof(with_control), out, sizeof(out)) < 0, "control byte rejected");
    const uint8_t truncated_utf8[] = {'C', 0xC3};
    CHECK(omi_device_characteristic_text(truncated_utf8, sizeof(truncated_utf8), out, sizeof(out)) < 0, "truncated utf8 rejected");
    const uint8_t surrogate[] = {0xED, 0xA0, 0x80};
    CHECK(omi_device_characteristic_text(surrogate, sizeof(surrogate), out, sizeof(out)) < 0, "utf8-encoded surrogate rejected");
    const uint8_t overlong[] = {0xC0, 0x80};
    CHECK(omi_device_characteristic_text(overlong, sizeof(overlong), out, sizeof(out)) < 0, "overlong encoding rejected");

    // Buffer too small.
    CHECK_EQ_INT(omi_device_characteristic_text(model, sizeof(model), out, 4), -1, "small buffer rejected");
}

static void test_assembler() {
    uint16_t index = 0;
    std::vector<uint8_t> payload(1024);
    size_t payload_len = 0;
    int32_t codec_status = 0;

    void* assembler = omi_device_assembler_create();
    CHECK(assembler != nullptr, "assembler created");

    // Valid framed packets in order are accepted with their payloads.
    std::vector<uint8_t> first = raw_packet(0, {1, 2, 3});
    CHECK_EQ_INT(omi_device_assembler_classify(assembler, first.data(), first.size(), &index, payload.data(), payload.size(), &payload_len, &codec_status), OMI_DEVICE_PACKET_ACCEPTED, "first packet accepted");
    CHECK_EQ_INT(index, 0, "first index");
    CHECK_EQ_INT(payload_len, 3, "first payload length");
    CHECK_EQ_INT(payload[0], 1, "first payload byte 0");
    CHECK_EQ_INT(payload[2], 3, "first payload byte 2");

    std::vector<uint8_t> second = raw_packet(1, {4});
    CHECK_EQ_INT(omi_device_assembler_classify(assembler, second.data(), second.size(), &index, payload.data(), payload.size(), &payload_len, &codec_status), OMI_DEVICE_PACKET_ACCEPTED, "second packet accepted");
    CHECK_EQ_INT(index, 1, "second index");

    // Duplicates drop.
    std::vector<uint8_t> dupe = raw_packet(1, {4});
    CHECK_EQ_INT(omi_device_assembler_classify(assembler, dupe.data(), dupe.size(), &index, payload.data(), payload.size(), &payload_len, &codec_status), OMI_DEVICE_PACKET_DUPLICATE, "duplicate dropped");

    // Sequence wrap to 0 is a normal one-step delta.
    std::vector<uint8_t> top = raw_packet(65535, {1});
    CHECK_EQ_INT(omi_device_assembler_classify(assembler, top.data(), top.size(), &index, payload.data(), payload.size(), &payload_len, &codec_status), OMI_DEVICE_PACKET_ACCEPTED, "65535 accepted");
    std::vector<uint8_t> wrapped = raw_packet(0, {2});
    CHECK_EQ_INT(omi_device_assembler_classify(assembler, wrapped.data(), wrapped.size(), &index, payload.data(), payload.size(), &payload_len, &codec_status), OMI_DEVICE_PACKET_ACCEPTED, "wrap accepted");

    // Short frames.
    const uint8_t tiny[] = {0x01};
    CHECK_EQ_INT(omi_device_assembler_classify(assembler, tiny, 1, &index, payload.data(), payload.size(), &payload_len, &codec_status), OMI_DEVICE_PACKET_SHORT_FRAME, "short frame");
    CHECK_EQ_INT(omi_device_assembler_classify(assembler, nullptr, 0, &index, payload.data(), payload.size(), &payload_len, &codec_status), OMI_DEVICE_PACKET_SHORT_FRAME, "empty frame");

    // Bad sync bytes → OMI_STATUS_ERR_SYNC_BYTES (-2) through the codec
    // (fresh baseline, mirroring the Swift suite's second assembler).
    omi_device_assembler_reset(assembler);
    std::vector<uint8_t> bad_sync = raw_packet(0, {1});
    bad_sync[2] = 0x00;
    CHECK_EQ_INT(omi_device_assembler_classify(assembler, bad_sync.data(), bad_sync.size(), &index, payload.data(), payload.size(), &payload_len, &codec_status), OMI_DEVICE_PACKET_CODEC_INVALID, "bad sync invalid");
    CHECK_EQ_INT(codec_status, -2, "sync status from codec");

    // Corrupt CRC → OMI_STATUS_ERR_CHECKSUM (-3).
    omi_device_assembler_reset(assembler);
    std::vector<uint8_t> bad_crc = raw_packet(0, {1, 2});
    bad_crc[bad_crc.size() - 1] ^= 0xFF;
    CHECK_EQ_INT(omi_device_assembler_classify(assembler, bad_crc.data(), bad_crc.size(), &index, payload.data(), payload.size(), &payload_len, &codec_status), OMI_DEVICE_PACKET_CODEC_INVALID, "bad crc invalid");
    CHECK_EQ_INT(codec_status, -3, "crc status from codec");

    // Reset clears the baseline: index 0 accepted again.
    omi_device_assembler_reset(assembler);
    std::vector<uint8_t> restarted = raw_packet(0, {7});
    CHECK_EQ_INT(omi_device_assembler_classify(assembler, restarted.data(), restarted.size(), &index, payload.data(), payload.size(), &payload_len, &codec_status), OMI_DEVICE_PACKET_ACCEPTED, "post-reset accepted");

    omi_device_assembler_destroy(assembler);
}

static void test_capture_machine() {
    uint16_t index = 0;

    void* capture = omi_device_capture_create();
    CHECK(capture != nullptr, "capture created");
    CHECK_EQ_INT(omi_device_capture_stage(capture), OMI_DEVICE_STAGE_IDLE, "starts idle");
    CHECK_EQ_INT(omi_device_capture_is_capturing(capture), 0, "not capturing at idle");

    // Ingest before open is a no-op.
    std::vector<uint8_t> early = raw_packet(0, {1});
    CHECK_EQ_INT(omi_device_capture_ingest(capture, early.data(), early.size(), 5, &index), 0, "pre-open ingest ignored");

    CHECK_EQ_INT(omi_device_capture_open(capture, "dev-1", "Omi", 1, 1000), OMI_STATUS_OK, "open accepted");
    CHECK_EQ_INT(omi_device_capture_stage(capture), OMI_DEVICE_STAGE_WAITING, "waiting after open");
    CHECK_EQ_INT(omi_device_capture_is_capturing(capture), 1, "capturing after open");
    CHECK_EQ_INT(omi_device_capture_open(capture, "", nullptr, 1, 1000), OMI_STATUS_ERR_INVALID_PARAM, "empty device id refused");

    char text[128];
    CHECK_EQ_INT(omi_device_capture_device_id(capture, text, sizeof(text)), 5, "device id written");
    CHECK_EQ_STR(text, "dev-1", "device id value");
    CHECK_EQ_INT(omi_device_capture_device_name(capture, text, sizeof(text)), 3, "device name written");
    CHECK_EQ_STR(text, "Omi", "device name value");
    CHECK_EQ_INT(omi_device_capture_codec(capture), 1, "codec stored");

    // First accepted packet activates the capture.
    std::vector<uint8_t> first = raw_packet(0, {1, 2, 3});
    CHECK_EQ_INT(omi_device_capture_ingest(capture, first.data(), first.size(), 1050, &index), 1, "first packet accepted");
    CHECK_EQ_INT(index, 0, "first packet index");
    CHECK_EQ_INT(omi_device_capture_stage(capture), OMI_DEVICE_STAGE_ACTIVE, "active after first packet");

    // Rejected packets do not count.
    std::vector<uint8_t> dupe = raw_packet(0, {1, 2, 3});
    CHECK_EQ_INT(omi_device_capture_ingest(capture, dupe.data(), dupe.size(), 1060, &index), 0, "duplicate not accepted");
    const uint8_t tiny[] = {0x01};
    CHECK_EQ_INT(omi_device_capture_ingest(capture, tiny, 1, 1070, &index), 0, "short frame not accepted");

    // Handoff carries the batch and completes the capture.
    int64_t started = 0;
    int64_t ended = 0;
    size_t byte_count = 0;
    CHECK_EQ_INT(omi_device_capture_handoff(capture, 1200, &started, &ended, &byte_count), 1, "handoff performed");
    CHECK_EQ_INT(started, 1000, "handoff started at");
    CHECK_EQ_INT(ended, 1200, "handoff ended at");
    CHECK_EQ_INT(byte_count, 3, "handoff byte count");
    CHECK_EQ_INT(omi_device_capture_packet_count(capture), 1, "handoff packet count");
    uint16_t packet_index = 0;
    std::vector<uint8_t> packet_payload(64);
    size_t packet_len = 0;
    int64_t received_at = 0;
    CHECK_EQ_INT(omi_device_capture_packet_at(capture, 0, &packet_index, packet_payload.data(), packet_payload.size(), &packet_len, &received_at), OMI_STATUS_OK, "packet readable");
    CHECK_EQ_INT(packet_index, 0, "packet index readable");
    CHECK_EQ_INT(packet_len, 3, "packet payload length");
    CHECK_EQ_INT(received_at, 1050, "packet receipt time");
    CHECK_EQ_INT(omi_device_capture_packet_at(capture, 1, &packet_index, packet_payload.data(), packet_payload.size(), &packet_len, &received_at), OMI_STATUS_ERR_INVALID_PARAM, "out of range refused");
    CHECK_EQ_INT(omi_device_capture_stage(capture), OMI_DEVICE_STAGE_COMPLETED, "completed after handoff");
    CHECK_EQ_INT(omi_device_capture_ingest(capture, first.data(), first.size(), 1300, &index), 0, "post-completion ingest ignored");

    // Handoff without audio completes without a journal.
    CHECK_EQ_INT(omi_device_capture_open(capture, "dev-2", nullptr, 1, 10), OMI_STATUS_OK, "reopen accepted");
    CHECK_EQ_INT(omi_device_capture_device_name(capture, text, sizeof(text)), OMI_STATUS_ERR_INVALID_PARAM, "absent name reported");
    CHECK_EQ_INT(omi_device_capture_handoff(capture, 20, &started, &ended, &byte_count), 0, "empty handoff declines");
    CHECK_EQ_INT(omi_device_capture_stage(capture), OMI_DEVICE_STAGE_COMPLETED, "empty capture completed");
    CHECK_EQ_INT(omi_device_capture_packet_count(capture), 0, "no packets after empty handoff");

    // Failure is terminal.
    CHECK_EQ_INT(omi_device_capture_open(capture, "dev-3", nullptr, 1, 30), OMI_STATUS_OK, "reopen for failure");
    omi_device_capture_fail(capture);
    CHECK_EQ_INT(omi_device_capture_stage(capture), OMI_DEVICE_STAGE_FAILED, "failed stage");
    CHECK_EQ_INT(omi_device_capture_ingest(capture, first.data(), first.size(), 40, &index), 0, "failed capture ignores packets");
    CHECK_EQ_INT(omi_device_capture_handoff(capture, 50, &started, &ended, &byte_count), 0, "failed capture cannot hand off");

    // Reopen resets the batch and the sequence baseline.
    CHECK_EQ_INT(omi_device_capture_open(capture, "dev-4", "NotePin", 2, 60), OMI_STATUS_OK, "reopen resets");
    CHECK_EQ_INT(omi_device_capture_stage(capture), OMI_DEVICE_STAGE_WAITING, "reopened waiting");
    CHECK_EQ_INT(omi_device_capture_packet_count(capture), 0, "reopened empty");
    CHECK_EQ_INT(omi_device_capture_ingest(capture, raw_packet(0, {7}).data(), raw_packet(0, {7}).size(), 61, &index), 1, "index 0 accepted again");

    omi_device_capture_destroy(capture);
}

int main() {
    test_note_pin_advertisement();
    test_discovered_name();
    test_omi_like_filter();
    test_battery_persistence_rule();
    test_characteristic_text();
    test_assembler();
    test_capture_machine();
    if (failures == 0) {
        std::printf("omi_device: all tests passed\n");
        return 0;
    }
    std::printf("omi_device: %d failure(s)\n", failures);
    return 1;
}
