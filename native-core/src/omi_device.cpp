#include "omi_device.h"

#include <string>
#include <vector>

#include "omi_native_boundary.h"

// Portable BLE device logic (naming, energy rule, device-info parsing,
// packet assembly, capture state machine) shared by every platform client.
// Radio machinery stays in per-OS shims; this library holds only the rules,
// ported from the upstream maintained app/ios/Runner/Ble implementations.

namespace {

constexpr uint8_t kNotePinPayload[4] = {0x04, 0x56, 0xCF, 0x00};
constexpr uint16_t kPlaudManufacturerId = 93; // 0x5D, little-endian on air
constexpr size_t kMinFramedLen = 2 + 2;      // seq index + sync bytes

struct PacketRecord {
    uint16_t index = 0;
    std::vector<uint8_t> payload;
    int64_t received_at_ms = 0;
};

bool is_trim_whitespace(uint8_t byte) {
    return byte == 0x20 || byte == 0x0A || byte == 0x0D || byte == 0x09;
}

bool is_ascii_whitespace(uint8_t byte) {
    return byte == 0x20 || byte == 0x09 || byte == 0x0A || byte == 0x0D;
}

size_t copy_capped(const std::string& value, char* out, size_t out_cap) {
    if (out == nullptr || out_cap < value.size() + 1) {
        return static_cast<size_t>(-1);
    }
    value.copy(out, value.size());
    out[value.size()] = '\0';
    return value.size();
}

// Strict UTF-8 validation (rejects overlongs, surrogates, > U+10FFFF,
// truncated sequences) so byte round-trips match Swift's
// `String(decoding:as:)` re-encoding contract.
bool is_valid_utf8(const uint8_t* bytes, size_t len) {
    size_t i = 0;
    while (i < len) {
        const uint8_t lead = bytes[i];
        if (lead < 0x80) {
            i += 1;
            continue;
        }
        uint32_t codepoint = 0;
        int extra = 0;
        if ((lead & 0xE0) == 0xC0) {
            codepoint = lead & 0x1Fu;
            extra = 1;
        } else if ((lead & 0xF0) == 0xE0) {
            codepoint = lead & 0x0Fu;
            extra = 2;
        } else if ((lead & 0xF8) == 0xF0) {
            codepoint = lead & 0x07u;
            extra = 3;
        } else {
            return false;
        }
        if (i + extra >= len) return false;
        for (int k = 1; k <= extra; k++) {
            const uint8_t cont = bytes[i + k];
            if ((cont & 0xC0) != 0x80) return false;
            codepoint = (codepoint << 6) | (cont & 0x3Fu);
        }
        if ((extra == 1 && codepoint < 0x80) ||
            (extra == 2 && codepoint < 0x800) ||
            (extra == 3 && codepoint < 0x10000)) {
            return false;
        }
        if (codepoint >= 0xD800 && codepoint <= 0xDFFF) return false;
        if (codepoint > 0x10FFFF) return false;
        i += static_cast<size_t>(extra) + 1;
    }
    return true;
}

class AudioPacketAssembler {
public:
    void reset() { has_last_index_ = false; }

    int32_t classify(
        const uint8_t* raw, size_t raw_len, uint16_t* out_index,
        uint8_t* out_payload, size_t out_cap, size_t* out_payload_len,
        int32_t* out_codec_status
    ) {
        if (out_index == nullptr || out_payload_len == nullptr ||
            out_codec_status == nullptr) {
            return -1;
        }
        *out_codec_status = OMI_STATUS_OK;
        // Index + sync bytes minimum; the codec enforces the full framing.
        if (raw == nullptr || raw_len < kMinFramedLen) {
            return OMI_DEVICE_PACKET_SHORT_FRAME;
        }
        const uint16_t index =
            static_cast<uint16_t>(raw[0]) |
            static_cast<uint16_t>(static_cast<uint16_t>(raw[1]) << 8);
        if (has_last_index_) {
            const uint16_t delta =
                static_cast<uint16_t>(index - last_index_);
            if (delta == 0) {
                return OMI_DEVICE_PACKET_DUPLICATE;
            }
        }
        last_index_ = index;
        has_last_index_ = true;
        *out_index = index;

        // Framed body: 0xAA 0x55 + payload + 4-byte CRC32 big endian.
        const uint8_t* body = raw + 2;
        const size_t body_len = raw_len - 2;
        if (out_cap < body_len) {
            *out_codec_status = OMI_STATUS_ERR_BUFFER_OVERFLOW;
            return OMI_DEVICE_PACKET_CODEC_INVALID;
        }
        size_t payload_len = 0;
        const int32_t status = omi_normalize_packet(
            body, body_len, out_payload, out_cap, &payload_len);
        if (status != OMI_STATUS_OK) {
            *out_codec_status = status;
            return OMI_DEVICE_PACKET_CODEC_INVALID;
        }
        *out_payload_len = payload_len;
        return OMI_DEVICE_PACKET_ACCEPTED;
    }

private:
    bool has_last_index_ = false;
    uint16_t last_index_ = 0;
};

class CaptureMachine {
public:
    int32_t stage() const { return stage_; }

    bool is_capturing() const {
        return stage_ == OMI_DEVICE_STAGE_WAITING ||
            stage_ == OMI_DEVICE_STAGE_ACTIVE;
    }

    int open(
        const char* device_id, const char* device_name, int32_t codec,
        int64_t now_ms
    ) {
        if (device_id == nullptr || device_id[0] == '\0') {
            return OMI_STATUS_ERR_INVALID_PARAM;
        }
        device_id_ = device_id;
        device_name_ = device_name != nullptr ? std::string(device_name) : "";
        has_device_name_ = device_name != nullptr;
        codec_ = codec;
        started_at_ms_ = now_ms;
        stage_ = OMI_DEVICE_STAGE_WAITING;
        packets_.clear();
        byte_count_ = 0;
        assembler_.reset();
        handoff_.clear();
        return OMI_STATUS_OK;
    }

    int ingest(
        const uint8_t* raw, size_t raw_len, int64_t received_at_ms,
        uint16_t* out_index
    ) {
        if (out_index == nullptr) return -1;
        if (!is_capturing()) return 0;
        std::vector<uint8_t> payload(kMaxNotificationBytes);
        uint16_t index = 0;
        size_t payload_len = 0;
        int32_t codec_status = OMI_STATUS_OK;
        const int32_t kind = assembler_.classify(
            raw, raw_len, &index, payload.data(), payload.size(), &payload_len,
            &codec_status);
        if (kind != OMI_DEVICE_PACKET_ACCEPTED) return 0;
        payload.resize(payload_len);
        if (payload.empty()) return 0;
        if (stage_ == OMI_DEVICE_STAGE_WAITING) {
            stage_ = OMI_DEVICE_STAGE_ACTIVE;
        }
        PacketRecord record;
        record.index = index;
        record.payload = payload;
        record.received_at_ms = received_at_ms;
        byte_count_ += payload.size();
        packets_.push_back(std::move(record));
        *out_index = index;
        return 1;
    }

    void fail() {
        if (is_capturing()) stage_ = OMI_DEVICE_STAGE_FAILED;
    }

    int handoff(
        int64_t now_ms, int64_t* out_started_at_ms, int64_t* out_ended_at_ms,
        size_t* out_byte_count
    ) {
        if (out_started_at_ms == nullptr || out_ended_at_ms == nullptr ||
            out_byte_count == nullptr) {
            return -1;
        }
        if (!is_capturing()) return 0;
        if (packets_.empty()) {
            stage_ = OMI_DEVICE_STAGE_COMPLETED;
            return 0;
        }
        handoff_ = packets_;
        handoff_byte_count_ = byte_count_;
        *out_started_at_ms = started_at_ms_;
        *out_ended_at_ms = now_ms;
        *out_byte_count = byte_count_;
        stage_ = OMI_DEVICE_STAGE_COMPLETED;
        packets_.clear();
        byte_count_ = 0;
        return 1;
    }

    size_t handoff_packet_count() const { return handoff_.size(); }

    int handoff_packet_at(
        size_t position, uint16_t* out_index, uint8_t* out_payload,
        size_t out_cap, size_t* out_payload_len, int64_t* out_received_at_ms
    ) {
        if (out_index == nullptr || out_payload == nullptr ||
            out_payload_len == nullptr || out_received_at_ms == nullptr ||
            position >= handoff_.size()) {
            return OMI_STATUS_ERR_INVALID_PARAM;
        }
        const PacketRecord& record = handoff_[position];
        if (out_cap < record.payload.size()) {
            return OMI_STATUS_ERR_INVALID_PARAM;
        }
        std::copy(record.payload.begin(), record.payload.end(), out_payload);
        *out_index = record.index;
        *out_payload_len = record.payload.size();
        *out_received_at_ms = record.received_at_ms;
        return OMI_STATUS_OK;
    }

    const std::string& device_id() const { return device_id_; }
    const std::string& device_name() const { return device_name_; }
    bool has_device_name() const { return has_device_name_; }
    int32_t codec() const { return codec_; }
    size_t batch_count() const { return packets_.size(); }
    size_t batch_byte_count() const { return byte_count_; }
    int64_t started_at_ms() const {
        return stage_ == OMI_DEVICE_STAGE_IDLE ? 0 : started_at_ms_;
    }

private:
    // Audio notifications are bounded by the BLE ATT payload (~512 bytes);
    // keep headroom without dynamic allocation per call.
    static constexpr size_t kMaxNotificationBytes = 1024;

    int32_t stage_ = OMI_DEVICE_STAGE_IDLE;
    std::string device_id_;
    std::string device_name_;
    bool has_device_name_ = false;
    int32_t codec_ = 0;
    int64_t started_at_ms_ = 0;
    size_t byte_count_ = 0;
    std::vector<PacketRecord> packets_;
    AudioPacketAssembler assembler_;
    std::vector<PacketRecord> handoff_;
    size_t handoff_byte_count_ = 0;
};

} // namespace

extern "C" {

int omi_device_is_note_pin_advertisement(const uint8_t* data, size_t len) {
    if (data == nullptr || len < 2 + sizeof(kNotePinPayload)) return 0;
    const uint16_t manufacturer_id =
        static_cast<uint16_t>(data[0]) |
        static_cast<uint16_t>(static_cast<uint16_t>(data[1]) << 8);
    if (manufacturer_id != kPlaudManufacturerId) return 0;
    for (size_t i = 0; i < sizeof(kNotePinPayload); i++) {
        if (data[2 + i] != kNotePinPayload[i]) return 0;
    }
    return 1;
}

int omi_device_discovered_name(
    const char* advertised_local_name, const char* cached_name,
    const uint8_t* manufacturer_data, size_t manufacturer_data_len, char* out,
    size_t out_cap
) {
    auto trimmed = [](const char* name) -> std::string {
        if (name == nullptr) return "";
        std::string value(name);
        size_t begin = 0;
        size_t end = value.size();
        while (begin < end &&
               is_trim_whitespace(static_cast<uint8_t>(value[begin]))) {
            begin++;
        }
        while (end > begin &&
               is_trim_whitespace(static_cast<uint8_t>(value[end - 1]))) {
            end--;
        }
        return value.substr(begin, end - begin);
    };
    std::string resolved = trimmed(advertised_local_name);
    if (resolved.empty()) resolved = trimmed(cached_name);
    if (resolved.empty() &&
        omi_device_is_note_pin_advertisement(
            manufacturer_data, manufacturer_data_len) == 1) {
        resolved = "NotePin";
    }
    return static_cast<int>(copy_capped(resolved, out, out_cap));
}

int omi_device_is_omi_like(const char* name) {
    if (name == nullptr) return 0;
    std::string lowered(name);
    for (char& c : lowered) {
        if (c >= 'A' && c <= 'Z') c = static_cast<char>(c - 'A' + 'a');
    }
    return lowered.find("omi") != std::string::npos ||
        lowered.find("notepin") != std::string::npos
        ? 1
        : 0;
}

int omi_device_should_persist_battery_reading(
    int32_t previous_level, int has_previous_level,
    int64_t previous_timestamp_ms, int has_previous_timestamp_ms,
    int32_t level, int64_t now_ms
) {
    if (has_previous_level == 0 || has_previous_timestamp_ms == 0) return 1;
    if (level != previous_level) return 1;
    if (now_ms - previous_timestamp_ms >=
        OMI_DEVICE_BATTERY_HISTORY_MIN_INTERVAL_MS) {
        return 1;
    }
    return 0;
}

int omi_device_characteristic_text(
    const uint8_t* bytes, size_t len, char* out, size_t out_cap
) {
    if (bytes == nullptr) return OMI_STATUS_ERR_INVALID_PARAM;
    size_t begin = 0;
    size_t end = len;
    while (begin < end && is_ascii_whitespace(bytes[begin])) begin++;
    while (end > begin && is_ascii_whitespace(bytes[end - 1])) end--;
    if (begin == end) return OMI_STATUS_ERR_INVALID_PARAM;
    for (size_t i = begin; i < end; i++) {
        // Control bytes (including NUL padding) make the value invalid —
        // firmware bugs otherwise leak as garbage identity rows.
        if (bytes[i] < 0x20 || bytes[i] == 0x7F) {
            return OMI_STATUS_ERR_INVALID_PARAM;
        }
    }
    if (!is_valid_utf8(bytes + begin, end - begin)) {
        return OMI_STATUS_ERR_INVALID_PARAM;
    }
    std::string value(reinterpret_cast<const char*>(bytes + begin), end - begin);
    return static_cast<int>(copy_capped(value, out, out_cap));
}

void* omi_device_assembler_create(void) {
    return new (std::nothrow) AudioPacketAssembler();
}

void omi_device_assembler_destroy(void* assembler) {
    delete static_cast<AudioPacketAssembler*>(assembler);
}

void omi_device_assembler_reset(void* assembler) {
    if (assembler != nullptr) {
        static_cast<AudioPacketAssembler*>(assembler)->reset();
    }
}

int32_t omi_device_assembler_classify(
    void* assembler, const uint8_t* raw, size_t raw_len, uint16_t* out_index,
    uint8_t* out_payload, size_t out_cap, size_t* out_payload_len,
    int32_t* out_codec_status
) {
    if (assembler == nullptr) return -1;
    return static_cast<AudioPacketAssembler*>(assembler)
        ->classify(raw, raw_len, out_index, out_payload, out_cap,
                   out_payload_len, out_codec_status);
}

void* omi_device_capture_create(void) { return new (std::nothrow) CaptureMachine(); }

void omi_device_capture_destroy(void* machine) {
    delete static_cast<CaptureMachine*>(machine);
}

int32_t omi_device_capture_stage(void* machine) {
    return machine != nullptr ? static_cast<CaptureMachine*>(machine)->stage()
                              : OMI_DEVICE_STAGE_IDLE;
}

int omi_device_capture_is_capturing(void* machine) {
    return machine != nullptr && static_cast<CaptureMachine*>(machine)->is_capturing()
        ? 1
        : 0;
}

int omi_device_capture_open(
    void* machine, const char* device_id, const char* device_name,
    int32_t codec, int64_t now_ms
) {
    if (machine == nullptr) return OMI_STATUS_ERR_INVALID_PARAM;
    return static_cast<CaptureMachine*>(machine)->open(
        device_id, device_name, codec, now_ms);
}

int omi_device_capture_ingest(
    void* machine, const uint8_t* raw, size_t raw_len, int64_t received_at_ms,
    uint16_t* out_index
) {
    if (machine == nullptr) return -1;
    return static_cast<CaptureMachine*>(machine)->ingest(
        raw, raw_len, received_at_ms, out_index);
}

void omi_device_capture_fail(void* machine) {
    if (machine != nullptr) static_cast<CaptureMachine*>(machine)->fail();
}

int omi_device_capture_handoff(
    void* machine, int64_t now_ms, int64_t* out_started_at_ms,
    int64_t* out_ended_at_ms, size_t* out_byte_count
) {
    if (machine == nullptr) return -1;
    return static_cast<CaptureMachine*>(machine)->handoff(
        now_ms, out_started_at_ms, out_ended_at_ms, out_byte_count);
}

size_t omi_device_capture_packet_count(void* machine) {
    return machine != nullptr
        ? static_cast<CaptureMachine*>(machine)->handoff_packet_count()
        : 0;
}

size_t omi_device_capture_batch_count(void* machine) {
    return machine != nullptr
        ? static_cast<CaptureMachine*>(machine)->batch_count()
        : 0;
}

size_t omi_device_capture_batch_byte_count(void* machine) {
    return machine != nullptr
        ? static_cast<CaptureMachine*>(machine)->batch_byte_count()
        : 0;
}

int64_t omi_device_capture_started_at_ms(void* machine) {
    return machine != nullptr
        ? static_cast<CaptureMachine*>(machine)->started_at_ms()
        : 0;
}

int omi_device_capture_packet_at(
    void* machine, size_t position, uint16_t* out_index, uint8_t* out_payload,
    size_t out_cap, size_t* out_payload_len, int64_t* out_received_at_ms
) {
    if (machine == nullptr) return OMI_STATUS_ERR_INVALID_PARAM;
    return static_cast<CaptureMachine*>(machine)->handoff_packet_at(
        position, out_index, out_payload, out_cap, out_payload_len,
        out_received_at_ms);
}

int omi_device_capture_device_id(void* machine, char* out, size_t out_cap) {
    if (machine == nullptr) return OMI_STATUS_ERR_INVALID_PARAM;
    return static_cast<int>(copy_capped(
        static_cast<CaptureMachine*>(machine)->device_id(), out, out_cap));
}

int omi_device_capture_device_name(void* machine, char* out, size_t out_cap) {
    if (machine == nullptr) return OMI_STATUS_ERR_INVALID_PARAM;
    const CaptureMachine* capture = static_cast<CaptureMachine*>(machine);
    if (!capture->has_device_name()) return OMI_STATUS_ERR_INVALID_PARAM;
    return static_cast<int>(
        copy_capped(capture->device_name(), out, out_cap));
}

int32_t omi_device_capture_codec(void* machine) {
    return machine != nullptr ? static_cast<CaptureMachine*>(machine)->codec()
                              : 0;
}

} // extern "C"
