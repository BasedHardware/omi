#pragma once

#include <windows.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <audiopolicy.h>
#include <comdef.h>
#include <functiondiscoverykeys_devpkey.h>
#include <vector>
#include <memory>
#include <thread>
#include <atomic>
#include <flutter/method_channel.h>
#include <flutter/plugin_registrar_windows.h>
#include <flutter/standard_method_codec.h>
#include <flutter/encodable_value.h>
#include <chrono>

class WindowsAudioCapture {
public:
    WindowsAudioCapture();
    ~WindowsAudioCapture();

    // Main capture methods
    bool Initialize();
    bool StartCapture();
    bool StopCapture();
    void Cleanup();

    // Permission methods (simplified for Windows)
    std::string CheckMicrophonePermission();
    bool RequestMicrophonePermission();
    std::string CheckScreenCapturePermission(); // Always granted on Windows
    bool RequestScreenCapturePermission();
    
    // Other permissions (not applicable on Windows but needed for API compatibility)
    std::string CheckBluetoothPermission() { return "granted"; }
    bool RequestBluetoothPermission() { return true; }
    std::string CheckLocationPermission();
    bool RequestLocationPermission();
    std::string CheckNotificationPermission();
    bool RequestNotificationPermission();

    // Set Flutter method channel for sending data back
    void SetMethodChannel(std::shared_ptr<flutter::MethodChannel<flutter::EncodableValue>> channel);

private:
    // WASAPI interfaces
    IMMDeviceEnumerator* device_enumerator_;
    IMMDevice* microphone_device_;
    IMMDevice* loopback_device_;
    IAudioClient* microphone_client_;
    IAudioClient* loopback_client_;
    IAudioCaptureClient* microphone_capture_;
    IAudioCaptureClient* loopback_capture_;

    // Audio format info
    WAVEFORMATEX* microphone_format_;
    WAVEFORMATEX* loopback_format_;
    WAVEFORMATEX* output_format_;

    // Threading
    std::thread capture_thread_;
    std::atomic<bool> is_capturing_;
    std::atomic<bool> should_stop_;

    // Method channel for communication with Flutter
    std::shared_ptr<flutter::MethodChannel<flutter::EncodableValue>> method_channel_;
    
    // Accumulation buffers for proper timing
    std::vector<float> mic_accumulator_;
    std::vector<float> system_accumulator_;
    
    // Timing for packet generation
    std::chrono::steady_clock::time_point last_packet_time_;
    static const int TARGET_PACKET_INTERVAL_MS = 100; // Send packets every 100ms
    
    // Device change detection and recovery
    std::atomic<bool> device_invalidated_;
    std::chrono::steady_clock::time_point last_device_check_;
    static const int DEVICE_CHECK_INTERVAL_MS = 4000; // Check device health every 4 seconds

    // Audio format for Flutter output
    static const int FLUTTER_SAMPLE_RATE = 16000;
    static const int FLUTTER_CHANNELS = 1;
    static const int FLUTTER_BITS_PER_SAMPLE = 16;

    // Private methods
    bool InitializeWASAPI();
    bool InitializeMicrophone();
    bool InitializeLoopback();
    bool CreateOutputFormat();
    void CaptureLoop();
    void ProcessAudioBuffers();
    void SendAudioFormat();
    void SendAudioData(const std::vector<uint8_t>& data);
    void SendError(const std::string& error_type, const std::string& message);
    
    // Audio processing helpers
    void ProcessMicrophoneData(BYTE* data, UINT32 frames, float* output, int max_frames);
    void ProcessSystemAudioData(BYTE* data, UINT32 frames, float* output, int max_frames);
    void MixAudioSamples(const float* mic_samples, const float* system_samples, 
                        float* output_samples, int frame_count, int mic_channels, int system_channels);
    void ConvertToInt16(const float* input, int16_t* output, int sample_count);
    void ResampleAudio(const float* input, int input_frames, int input_rate,
                      float* output, int output_frames, int output_rate);
    
    // Device change handling
    bool DetectDeviceChanges();
    bool RecoverFromDeviceChange();
    bool ReinitializeAudioDevices();
    void CleanupAudioClients();
    
    // Utility methods
    std::string HResultToString(HRESULT hr);
    void SafeRelease(IUnknown** ppunk);
}; 