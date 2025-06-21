#include "windows_audio_capture.h"
#include <iostream>
#include <algorithm>
#include <cmath>
#include <locale>
#include <windows.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <audiopolicy.h>
#include <functiondiscoverykeys_devpkey.h>
#include <propvarutil.h>
#include <propsys.h>
#include <shellapi.h>  // For ShellExecute
#include <winreg.h>    // For registry functions


const CLSID CLSID_MMDeviceEnumerator = __uuidof(MMDeviceEnumerator);
const IID IID_IMMDeviceEnumerator = __uuidof(IMMDeviceEnumerator);
const IID IID_IAudioClient = __uuidof(IAudioClient);
const IID IID_IAudioCaptureClient = __uuidof(IAudioCaptureClient);

WindowsAudioCapture::WindowsAudioCapture()
    : device_enumerator_(nullptr)
    , microphone_device_(nullptr)
    , loopback_device_(nullptr)
    , microphone_client_(nullptr)
    , loopback_client_(nullptr)
    , microphone_capture_(nullptr)
    , loopback_capture_(nullptr)
    , microphone_format_(nullptr)
    , loopback_format_(nullptr)
    , output_format_(nullptr)
    , is_capturing_(false)
    , should_stop_(false)
    , device_invalidated_(false) {
}

WindowsAudioCapture::~WindowsAudioCapture() {
    Cleanup();
}

bool WindowsAudioCapture::Initialize() {
    std::cout << "Initializing Windows Audio Capture..." << std::endl;
    
    // Initialize COM - this might already be done by Flutter but it's safe to call again
    HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (FAILED(hr) && hr != RPC_E_CHANGED_MODE) {
        std::cout << "Failed to initialize COM: " << HResultToString(hr) << std::endl;
        return false;
    }

    if (!InitializeWASAPI()) {
        std::cout << "Failed to initialize WASAPI" << std::endl;
        return false;
    }

    if (!InitializeMicrophone()) {
        std::cout << "Failed to initialize microphone" << std::endl;
        return false;
    }

    if (!InitializeLoopback()) {
        std::cout << "Failed to initialize loopback" << std::endl;
        return false;
    }

    if (!CreateOutputFormat()) {
        std::cout << "Failed to create output format" << std::endl;
        return false;
    }

    std::cout << "Windows Audio Capture initialized successfully" << std::endl;
    return true;
}

bool WindowsAudioCapture::InitializeWASAPI() {
    HRESULT hr = CoCreateInstance(CLSID_MMDeviceEnumerator, nullptr, CLSCTX_ALL,
                                 IID_IMMDeviceEnumerator, (void**)&device_enumerator_);
    if (FAILED(hr)) {
        std::cout << "Failed to create device enumerator: " << HResultToString(hr) << std::endl;
        return false;
    }

    // DEBUG: Enumerate and display available audio devices
    std::cout << "=== AVAILABLE AUDIO DEVICES ===" << std::endl;
    
    // List capture devices (microphones)
    IMMDeviceCollection* capture_devices = nullptr;
    hr = device_enumerator_->EnumAudioEndpoints(eCapture, DEVICE_STATE_ACTIVE, &capture_devices);
    if (SUCCEEDED(hr)) {
        UINT capture_count = 0;
        capture_devices->GetCount(&capture_count);
        std::cout << "Available CAPTURE devices: " << capture_count << std::endl;
        
        for (UINT i = 0; i < capture_count; i++) {
            IMMDevice* device = nullptr;
            hr = capture_devices->Item(i, &device);
            if (SUCCEEDED(hr)) {
                LPWSTR device_id = nullptr;
                device->GetId(&device_id);
                
                IPropertyStore* props = nullptr;
                device->OpenPropertyStore(STGM_READ, &props);
                if (props) {
                    PROPVARIANT var_name;
                    PropVariantInit(&var_name);
                    props->GetValue(PKEY_Device_FriendlyName, &var_name);
                    
                    std::wcout << L"  [" << i << L"] " << var_name.pwszVal << L" (ID: " << device_id << L")" << std::endl;
                    
                    PropVariantClear(&var_name);
                    props->Release();
                }
                
                CoTaskMemFree(device_id);
                device->Release();
            }
        }
        capture_devices->Release();
    }
    
    // List render devices (speakers/headphones)
    IMMDeviceCollection* render_devices = nullptr;
    hr = device_enumerator_->EnumAudioEndpoints(eRender, DEVICE_STATE_ACTIVE, &render_devices);
    if (SUCCEEDED(hr)) {
        UINT render_count = 0;
        render_devices->GetCount(&render_count);
        std::cout << "Available RENDER devices: " << render_count << std::endl;
        
        for (UINT i = 0; i < render_count; i++) {
            IMMDevice* device = nullptr;
            hr = render_devices->Item(i, &device);
            if (SUCCEEDED(hr)) {
                LPWSTR device_id = nullptr;
                device->GetId(&device_id);
                
                IPropertyStore* props = nullptr;
                device->OpenPropertyStore(STGM_READ, &props);
                if (props) {
                    PROPVARIANT var_name;
                    PropVariantInit(&var_name);
                    props->GetValue(PKEY_Device_FriendlyName, &var_name);
                    
                    std::wcout << L"  [" << i << L"] " << var_name.pwszVal << L" (ID: " << device_id << L")" << std::endl;
                    
                    PropVariantClear(&var_name);
                    props->Release();
                }
                
                CoTaskMemFree(device_id);
                device->Release();
            }
        }
        render_devices->Release();
    }
    
    std::cout << "===============================" << std::endl;

    return true;
}

bool WindowsAudioCapture::InitializeMicrophone() {
    // Always use the system's default microphone device
    // The user can control which device is used through Windows sound settings
    HRESULT hr = device_enumerator_->GetDefaultAudioEndpoint(eCapture, eConsole, &microphone_device_);
    if (FAILED(hr)) {
        std::cout << "Failed to get default microphone device: " << HResultToString(hr) << std::endl;
        return false;
    }
    std::cout << "Using system default microphone device" << std::endl;

    // DEBUG: Show which microphone device was selected
    LPWSTR mic_device_id = nullptr;
    microphone_device_->GetId(&mic_device_id);
    IPropertyStore* mic_props = nullptr;
    microphone_device_->OpenPropertyStore(STGM_READ, &mic_props);
    if (mic_props) {
        PROPVARIANT var_name;
        PropVariantInit(&var_name);
        mic_props->GetValue(PKEY_Device_FriendlyName, &var_name);
        std::wcout << L"SELECTED MICROPHONE: " << var_name.pwszVal << std::endl;
        PropVariantClear(&var_name);
        mic_props->Release();
    }
    CoTaskMemFree(mic_device_id);

    hr = microphone_device_->Activate(IID_IAudioClient, CLSCTX_ALL, nullptr, (void**)&microphone_client_);
    if (FAILED(hr)) {
        std::cout << "Failed to activate microphone client: " << HResultToString(hr) << std::endl;
        return false;
    }

    hr = microphone_client_->GetMixFormat(&microphone_format_);
    if (FAILED(hr)) {
        std::cout << "Failed to get microphone mix format: " << HResultToString(hr) << std::endl;
        return false;
    }

    // DEBUG: Print detailed microphone format information
    std::cout << "=== MICROPHONE FORMAT DEBUG ===" << std::endl;
    std::cout << "Hardware sample rate: " << microphone_format_->nSamplesPerSec << "Hz" << std::endl;
    std::cout << "Hardware channels: " << microphone_format_->nChannels << std::endl;
    std::cout << "Hardware bits per sample: " << microphone_format_->wBitsPerSample << std::endl;
    std::cout << "Target output rate: " << FLUTTER_SAMPLE_RATE << "Hz" << std::endl;
    std::cout << "Rate conversion needed: " << (microphone_format_->nSamplesPerSec != FLUTTER_SAMPLE_RATE ? "YES" : "NO") << std::endl;
    std::cout << "===============================" << std::endl;

    // Ensure we're using float format for easier processing
    if (microphone_format_->wFormatTag != WAVE_FORMAT_EXTENSIBLE) {
        std::cout << "Microphone format is not extensible, using basic PCM" << std::endl;
    }

    // Initialize microphone client
    REFERENCE_TIME buffer_duration = 10000000; // 1 second
    hr = microphone_client_->Initialize(AUDCLNT_SHAREMODE_SHARED, 0, buffer_duration, 0, microphone_format_, nullptr);
    if (FAILED(hr)) {
        std::cout << "Failed to initialize microphone client: " << HResultToString(hr) << std::endl;
        return false;
    }

    hr = microphone_client_->GetService(IID_IAudioCaptureClient, (void**)&microphone_capture_);
    if (FAILED(hr)) {
        std::cout << "Failed to get microphone capture service: " << HResultToString(hr) << std::endl;
        return false;
    }

    std::cout << "Microphone initialized: " << microphone_format_->nSamplesPerSec << "Hz, " 
              << microphone_format_->nChannels << " channels, " 
              << microphone_format_->wBitsPerSample << " bits" << std::endl;

    return true;
}

bool WindowsAudioCapture::InitializeLoopback() {
    // Always use the system's default render device for loopback capture
    // This captures audio from whatever the user is actually hearing
    HRESULT hr = device_enumerator_->GetDefaultAudioEndpoint(eRender, eConsole, &loopback_device_);
    if (FAILED(hr)) {
        std::cout << "Failed to get default render device: " << HResultToString(hr) << std::endl;
        return false;
    }
    std::cout << "Using system default render device for loopback capture" << std::endl;

    // DEBUG: Show which render device was selected for loopback
    LPWSTR render_device_id = nullptr;
    loopback_device_->GetId(&render_device_id);
    IPropertyStore* render_props = nullptr;
    loopback_device_->OpenPropertyStore(STGM_READ, &render_props);
    if (render_props) {
        PROPVARIANT var_name;
        PropVariantInit(&var_name);
        render_props->GetValue(PKEY_Device_FriendlyName, &var_name);
        std::wcout << L"SELECTED RENDER DEVICE (for loopback): " << var_name.pwszVal << std::endl;
        PropVariantClear(&var_name);
        render_props->Release();
    }
    CoTaskMemFree(render_device_id);

    hr = loopback_device_->Activate(IID_IAudioClient, CLSCTX_ALL, nullptr, (void**)&loopback_client_);
    if (FAILED(hr)) {
        std::cout << "Failed to activate loopback client: " << HResultToString(hr) << std::endl;
        return false;
    }

    hr = loopback_client_->GetMixFormat(&loopback_format_);
    if (FAILED(hr)) {
        std::cout << "Failed to get loopback mix format: " << HResultToString(hr) << std::endl;
        return false;
    }

    // DEBUG: Print detailed loopback format information
    std::cout << "=== SYSTEM AUDIO FORMAT DEBUG ===" << std::endl;
    std::cout << "Hardware sample rate: " << loopback_format_->nSamplesPerSec << "Hz" << std::endl;
    std::cout << "Hardware channels: " << loopback_format_->nChannels << std::endl;
    std::cout << "Hardware bits per sample: " << loopback_format_->wBitsPerSample << std::endl;
    std::cout << "Target output rate: " << FLUTTER_SAMPLE_RATE << "Hz" << std::endl;
    std::cout << "Rate conversion needed: " << (loopback_format_->nSamplesPerSec != FLUTTER_SAMPLE_RATE ? "YES" : "NO") << std::endl;
    std::cout << "==================================" << std::endl;

    // Initialize loopback client with loopback flag
    REFERENCE_TIME buffer_duration = 10000000; // 1 second
    hr = loopback_client_->Initialize(AUDCLNT_SHAREMODE_SHARED, AUDCLNT_STREAMFLAGS_LOOPBACK, 
                                     buffer_duration, 0, loopback_format_, nullptr);
    if (FAILED(hr)) {
        std::cout << "Failed to initialize loopback client: " << HResultToString(hr) << std::endl;
        return false;
    }

    hr = loopback_client_->GetService(IID_IAudioCaptureClient, (void**)&loopback_capture_);
    if (FAILED(hr)) {
        std::cout << "Failed to get loopback capture service: " << HResultToString(hr) << std::endl;
        return false;
    }

    std::cout << "Loopback initialized: " << loopback_format_->nSamplesPerSec << "Hz, " 
              << loopback_format_->nChannels << " channels, " 
              << loopback_format_->wBitsPerSample << " bits" << std::endl;

    return true;
}

bool WindowsAudioCapture::CreateOutputFormat() {
    output_format_ = (WAVEFORMATEX*)CoTaskMemAlloc(sizeof(WAVEFORMATEX));
    if (!output_format_) {
        return false;
    }

    output_format_->wFormatTag = WAVE_FORMAT_PCM;
    output_format_->nChannels = FLUTTER_CHANNELS;
    output_format_->nSamplesPerSec = FLUTTER_SAMPLE_RATE;
    output_format_->wBitsPerSample = FLUTTER_BITS_PER_SAMPLE;
    output_format_->nBlockAlign = (output_format_->nChannels * output_format_->wBitsPerSample) / 8;
    output_format_->nAvgBytesPerSec = output_format_->nSamplesPerSec * output_format_->nBlockAlign;
    output_format_->cbSize = 0;

    std::cout << "Output format: " << FLUTTER_SAMPLE_RATE << "Hz, " << FLUTTER_CHANNELS << " channels, " 
              << FLUTTER_BITS_PER_SAMPLE << " bits" << std::endl;

    return true;
}

bool WindowsAudioCapture::StartCapture() {
    if (is_capturing_) {
        return true;
    }

    should_stop_ = false;
    device_invalidated_ = false;

    // Send audio format to Flutter
    SendAudioFormat();

    // Start WASAPI clients
    HRESULT hr = microphone_client_->Start();
    if (FAILED(hr)) {
        std::cout << "Failed to start microphone client: " << HResultToString(hr) << std::endl;
        return false;
    }

    hr = loopback_client_->Start();
    if (FAILED(hr)) {
        std::cout << "Failed to start loopback client: " << HResultToString(hr) << std::endl;
        microphone_client_->Stop();
        return false;
    }

    is_capturing_ = true;

    // Start capture thread
    capture_thread_ = std::thread(&WindowsAudioCapture::CaptureLoop, this);

    std::cout << "Audio capture started" << std::endl;
    return true;
}

bool WindowsAudioCapture::StopCapture() {
    if (!is_capturing_) {
        return true;
    }

    should_stop_ = true;
    is_capturing_ = false;

    // Stop WASAPI clients
    if (microphone_client_) {
        microphone_client_->Stop();
    }
    if (loopback_client_) {
        loopback_client_->Stop();
    }

    // Wait for capture thread to finish
    if (capture_thread_.joinable()) {
        capture_thread_.join();
    }

    // Notify Flutter that audio stream ended
    if (method_channel_) {
        method_channel_->InvokeMethod("audioStreamEnded", nullptr);
    }

    std::cout << "Audio capture stopped" << std::endl;
    return true;
}

void WindowsAudioCapture::CaptureLoop() {
    const int target_packet_frames = FLUTTER_SAMPLE_RATE / 10; // 100ms at 16kHz = 1600 frames
    const int target_packet_samples = target_packet_frames * FLUTTER_CHANNELS;
    
    std::vector<float> mixed_buffer(target_packet_samples);
    std::vector<int16_t> output_buffer(target_packet_samples);
    
    // Clear accumulation buffers
    mic_accumulator_.clear();
    system_accumulator_.clear();
    
    // Initialize packet timing
    last_packet_time_ = std::chrono::steady_clock::now();
    last_device_check_ = std::chrono::steady_clock::now();

    std::cout << "=== IMPROVED CAPTURE LOOP DEBUG ===" << std::endl;
    std::cout << "Target packet size: " << target_packet_frames << " frames (" << target_packet_samples << " samples)" << std::endl;
    std::cout << "Accumulation-based timing enabled" << std::endl;
    std::cout << "Packet interval: " << TARGET_PACKET_INTERVAL_MS << "ms" << std::endl;
    std::cout << "Device check interval: " << DEVICE_CHECK_INTERVAL_MS << "ms" << std::endl;
    std::cout << "====================================" << std::endl;
    std::cout << "Capture loop started" << std::endl;

    int debug_counter = 0;
    int packets_sent = 0;
    
    while (!should_stop_) {
        try {
            bool got_new_data = false;

            // === MICROPHONE CAPTURE ===
            UINT32 mic_frames_available = 0;
            BYTE* mic_data = nullptr;
            DWORD mic_flags = 0;
            
            HRESULT hr = microphone_capture_->GetNextPacketSize(&mic_frames_available);
            if (SUCCEEDED(hr) && mic_frames_available > 0) {
                hr = microphone_capture_->GetBuffer(&mic_data, &mic_frames_available, &mic_flags, nullptr, nullptr);
                if (SUCCEEDED(hr)) {
                    if (!(mic_flags & AUDCLNT_BUFFERFLAGS_SILENT)) {
                        // Calculate the exact number of output frames after resampling
                        int resampled_frames = static_cast<int>(
                            static_cast<double>(mic_frames_available) * FLUTTER_SAMPLE_RATE / microphone_format_->nSamplesPerSec + 0.5
                        );
                        
                        // Create temporary buffer for resampled data
                        std::vector<float> temp_resampled(resampled_frames);
                        ProcessMicrophoneData(mic_data, mic_frames_available, temp_resampled.data(), resampled_frames);
                        
                        // Add to accumulator
                        mic_accumulator_.insert(mic_accumulator_.end(), temp_resampled.begin(), temp_resampled.end());
                        got_new_data = true;
                        
                    }
                    microphone_capture_->ReleaseBuffer(mic_frames_available);
                }
            }

            // === SYSTEM AUDIO CAPTURE ===
            UINT32 system_frames_available = 0;
            BYTE* system_data = nullptr;
            DWORD system_flags = 0;
            
            hr = loopback_capture_->GetNextPacketSize(&system_frames_available);
            if (SUCCEEDED(hr) && system_frames_available > 0) {
                hr = loopback_capture_->GetBuffer(&system_data, &system_frames_available, &system_flags, nullptr, nullptr);
                if (SUCCEEDED(hr)) {
                    if (!(system_flags & AUDCLNT_BUFFERFLAGS_SILENT)) {
                        // Calculate the exact number of output frames after resampling
                        int resampled_frames = static_cast<int>(
                            static_cast<double>(system_frames_available) * FLUTTER_SAMPLE_RATE / loopback_format_->nSamplesPerSec + 0.5
                        );
                        
                        // Create temporary buffer for resampled data
                        std::vector<float> temp_resampled(resampled_frames);
                        ProcessSystemAudioData(system_data, system_frames_available, temp_resampled.data(), resampled_frames);
                        
                        // Add to accumulator
                        system_accumulator_.insert(system_accumulator_.end(), temp_resampled.begin(), temp_resampled.end());
                        got_new_data = true;
                        
                    }
                    loopback_capture_->ReleaseBuffer(system_frames_available);
                } else {
                    // Check for device invalidation error
                    if (hr == AUDCLNT_E_DEVICE_INVALIDATED) {
                        std::cout << "SYS: Device invalidated (0x" << std::hex << hr << std::dec << ") - attempting recovery..." << std::endl;
                        device_invalidated_ = true;
                    } else if (debug_counter % 200 == 0) {
                        std::cout << "SYS: Failed to get buffer: " << HResultToString(hr) << std::endl;
                    }
                }
            } else {
                // Check for device invalidation error in GetNextPacketSize
                if (FAILED(hr)) {
                    if (hr == AUDCLNT_E_DEVICE_INVALIDATED) {
                        std::cout << "SYS: Device invalidated during GetNextPacketSize (0x" << std::hex << hr << std::dec << ") - attempting recovery..." << std::endl;
                        device_invalidated_ = true;
                    } else if (debug_counter % 500 == 0) {
                        std::cout << "SYS: GetNextPacketSize failed: " << HResultToString(hr) << std::endl;
                    }
                } else if (debug_counter % 500 == 0) {
                    std::cout << "SYS: No packets available (frames=" << system_frames_available << ")" << std::endl;
                }
            }
            
            // === DEVICE CHANGE DETECTION AND RECOVERY ===
            auto device_check_time = std::chrono::steady_clock::now();
            auto time_since_device_check = std::chrono::duration_cast<std::chrono::milliseconds>(device_check_time - last_device_check_).count();
            
            if (device_invalidated_ || time_since_device_check >= DEVICE_CHECK_INTERVAL_MS) {
                if (device_invalidated_) {
                    std::cout << "DEVICE RECOVERY: Attempting to recover from device invalidation..." << std::endl;
                    if (RecoverFromDeviceChange()) {
                        std::cout << "DEVICE RECOVERY: Successfully recovered from device change!" << std::endl;
                        device_invalidated_ = false;
                    } else {
                        std::cout << "DEVICE RECOVERY: Failed to recover - continuing with current devices" << std::endl;
                        device_invalidated_ = false; // Reset flag to prevent spam
                    }
                } else if (DetectDeviceChanges()) {
                    std::cout << "DEVICE RECOVERY: Detected device change - attempting to switch to new preferred device..." << std::endl;
                    if (RecoverFromDeviceChange()) {
                        std::cout << "DEVICE RECOVERY: Successfully switched to new device!" << std::endl;
                    } else {
                        std::cout << "DEVICE RECOVERY: Failed to switch - continuing with current devices" << std::endl;
                    }
                }
                last_device_check_ = device_check_time;
            }

            // === PACKET GENERATION WITH TEMPORAL SYNCHRONIZATION ===
            // Always try to generate packets to maintain timing, pad with silence if needed
            
            // Check if either accumulator has enough data to generate a packet
            bool mic_has_enough = mic_accumulator_.size() >= target_packet_frames;
            bool sys_has_enough = system_accumulator_.size() >= target_packet_frames;
            
            // Check if enough time has passed to force a packet (prevent accumulator overflow)
            auto current_time = std::chrono::steady_clock::now();
            auto time_since_last_packet = std::chrono::duration_cast<std::chrono::milliseconds>(current_time - last_packet_time_).count();
            bool timeout_reached = time_since_last_packet >= TARGET_PACKET_INTERVAL_MS;
            
            if (mic_has_enough || sys_has_enough || timeout_reached) {
                // Prepare mic packet (use available data or silence)
                std::vector<float> mic_packet(target_packet_frames, 0.0f);
                if (mic_accumulator_.size() >= target_packet_frames) {
                    std::copy(mic_accumulator_.begin(), mic_accumulator_.begin() + target_packet_frames, mic_packet.begin());
                    mic_accumulator_.erase(mic_accumulator_.begin(), mic_accumulator_.begin() + target_packet_frames);
                } else if (!mic_accumulator_.empty()) {
                    // Use what we have and pad with silence
                    size_t available = mic_accumulator_.size();
                    std::copy(mic_accumulator_.begin(), mic_accumulator_.end(), mic_packet.begin());
                    mic_accumulator_.clear();
                    
                    if (debug_counter % 100 == 0) {
                        std::cout << "MIC: Padding " << (target_packet_frames - available) << " frames with silence" << std::endl;
                    }
                }
                // else: mic_packet remains all zeros (silence)
                
                // Prepare system packet (use available data or silence)
                std::vector<float> system_packet(target_packet_frames, 0.0f);
                if (system_accumulator_.size() >= target_packet_frames) {
                    std::copy(system_accumulator_.begin(), system_accumulator_.begin() + target_packet_frames, system_packet.begin());
                    system_accumulator_.erase(system_accumulator_.begin(), system_accumulator_.begin() + target_packet_frames);
                } else if (!system_accumulator_.empty()) {
                    // Use what we have and pad with silence
                    size_t available = system_accumulator_.size();
                    std::copy(system_accumulator_.begin(), system_accumulator_.end(), system_packet.begin());
                    system_accumulator_.clear();
                    
                    if (debug_counter % 100 == 0) {
                        std::cout << "SYS: Padding " << (target_packet_frames - available) << " frames with silence" << std::endl;
                    }
                }
                // else: system_packet remains all zeros (silence)
                
                // Mix the audio (both packets are guaranteed to be target_packet_frames long)
                MixAudioSamples(mic_packet.data(), system_packet.data(), mixed_buffer.data(), 
                              target_packet_frames, 1, 1);
                
                // Convert to 16-bit and send
                ConvertToInt16(mixed_buffer.data(), output_buffer.data(), target_packet_samples);
                
                std::vector<uint8_t> byte_buffer(output_buffer.size() * sizeof(int16_t));
                std::memcpy(byte_buffer.data(), output_buffer.data(), byte_buffer.size());
                SendAudioData(byte_buffer);
                
                packets_sent++;
                last_packet_time_ = current_time; // Update timing
                
                if (packets_sent % 25 == 0) { // Every ~2.5 seconds
                    std::cout << "SENT PACKET #" << packets_sent << ": " << target_packet_frames 
                              << " frames. Remaining: mic=" << mic_accumulator_.size() 
                              << ", sys=" << system_accumulator_.size();
                    if (timeout_reached) std::cout << " (TIMEOUT)";
                    std::cout << std::endl;
                }
            }

            debug_counter++;

        } catch (const std::exception& e) {
            std::cout << "Exception in capture loop: " << e.what() << std::endl;
            SendError("captureError", e.what());
            break;
        }

        // Short sleep for responsive data gathering
        Sleep(5); // 5ms sleep for high responsiveness
    }

    std::cout << "Capture loop ended. Total packets sent: " << packets_sent << std::endl;
}

void WindowsAudioCapture::ProcessMicrophoneData(BYTE* data, UINT32 frames, float* output, int max_frames) {
    if (!data || !output || frames == 0) return;
    
    // First convert to mono float at original sample rate
    std::vector<float> temp_buffer(frames);
    
    // Handle different audio formats
    if (microphone_format_->wBitsPerSample == 16) {
        // 16-bit PCM
        int16_t* samples = reinterpret_cast<int16_t*>(data);
        int channels = microphone_format_->nChannels;
        
        if (channels == 1) {
            // Mono - copy directly with conversion to float
            for (UINT32 i = 0; i < frames; ++i) {
                temp_buffer[i] = samples[i] / 32768.0f;
            }
        } else {
            // Multi-channel - mix to mono
            for (UINT32 i = 0; i < frames; ++i) {
                float sum = 0.0f;
                for (int ch = 0; ch < channels; ++ch) {
                    sum += samples[i * channels + ch] / 32768.0f;
                }
                temp_buffer[i] = sum / channels;
            }
        }
    } else if (microphone_format_->wBitsPerSample == 32) {
        // 32-bit float
        float* samples = reinterpret_cast<float*>(data);
        int channels = microphone_format_->nChannels;
        
        if (channels == 1) {
            // Mono - copy directly
            for (UINT32 i = 0; i < frames; ++i) {
                temp_buffer[i] = samples[i];
            }
        } else {
            // Multi-channel - mix to mono
            for (UINT32 i = 0; i < frames; ++i) {
                float sum = 0.0f;
                for (int ch = 0; ch < channels; ++ch) {
                    sum += samples[i * channels + ch];
                }
                temp_buffer[i] = sum / channels;
            }
        }
    }
    
    // Now resample from hardware rate to target rate
    if (microphone_format_->nSamplesPerSec != FLUTTER_SAMPLE_RATE) {
        ResampleAudio(temp_buffer.data(), frames, microphone_format_->nSamplesPerSec,
                     output, max_frames, FLUTTER_SAMPLE_RATE);
    } else {
        // No resampling needed, just copy
        int copy_frames = (static_cast<int>(frames) < max_frames) ? static_cast<int>(frames) : max_frames;
        std::copy(temp_buffer.begin(), temp_buffer.begin() + copy_frames, output);
    }
}

void WindowsAudioCapture::ProcessSystemAudioData(BYTE* data, UINT32 frames, float* output, int max_frames) {
    if (!data || !output || frames == 0) return;
    
    // First convert to mono float at original sample rate
    std::vector<float> temp_buffer(frames);
    
    // Handle different audio formats
    if (loopback_format_->wBitsPerSample == 16) {
        // 16-bit PCM
        int16_t* samples = reinterpret_cast<int16_t*>(data);
        int channels = loopback_format_->nChannels;
        
        if (channels == 1) {
            // Mono - copy directly with conversion to float
            for (UINT32 i = 0; i < frames; ++i) {
                temp_buffer[i] = samples[i] / 32768.0f;
            }
        } else {
            // Multi-channel - mix to mono
            for (UINT32 i = 0; i < frames; ++i) {
                float sum = 0.0f;
                for (int ch = 0; ch < channels; ++ch) {
                    sum += samples[i * channels + ch] / 32768.0f;
                }
                temp_buffer[i] = sum / channels;
            }
        }
    } else if (loopback_format_->wBitsPerSample == 32) {
        // 32-bit float
        float* samples = reinterpret_cast<float*>(data);
        int channels = loopback_format_->nChannels;
        
        if (channels == 1) {
            // Mono - copy directly
            for (UINT32 i = 0; i < frames; ++i) {
                temp_buffer[i] = samples[i];
            }
        } else {
            // Multi-channel - mix to mono
            for (UINT32 i = 0; i < frames; ++i) {
                float sum = 0.0f;
                for (int ch = 0; ch < channels; ++ch) {
                    sum += samples[i * channels + ch];
                }
                temp_buffer[i] = sum / channels;
            }
        }
    }
    
    // Now resample from hardware rate to target rate
    if (loopback_format_->nSamplesPerSec != FLUTTER_SAMPLE_RATE) {
        ResampleAudio(temp_buffer.data(), frames, loopback_format_->nSamplesPerSec,
                     output, max_frames, FLUTTER_SAMPLE_RATE);
    } else {
        // No resampling needed, just copy
        int copy_frames = (static_cast<int>(frames) < max_frames) ? static_cast<int>(frames) : max_frames;
        std::copy(temp_buffer.begin(), temp_buffer.begin() + copy_frames, output);
    }
}

void WindowsAudioCapture::MixAudioSamples(const float* mic_samples, const float* system_samples, 
                                         float* output_samples, int frame_count, int mic_channels, int system_channels) {
    for (int i = 0; i < frame_count; ++i) {
        // Mix with appropriate levels - microphone at 80%, system at 70%
        float mic_sample = mic_samples[i] * 0.8f;
        float system_sample = system_samples[i] * 0.7f;
        
        // Simple additive mixing with soft clipping to prevent harsh distortion
        float mixed = mic_sample + system_sample;
        
        // Soft clipping using tanh for more natural limiting
        if (mixed > 1.0f || mixed < -1.0f) {
            mixed = std::tanh(mixed * 0.7f);
        }
        
        output_samples[i] = mixed;
    }
}

void WindowsAudioCapture::ConvertToInt16(const float* input, int16_t* output, int sample_count) {
    for (int i = 0; i < sample_count; ++i) {
        float sample = input[i];
        // Clamp to [-1.0, 1.0] range
        if (sample > 1.0f) sample = 1.0f;
        if (sample < -1.0f) sample = -1.0f;
        
        // Convert to 16-bit integer
        output[i] = static_cast<int16_t>(sample * 32767.0f);
    }
}

void WindowsAudioCapture::ResampleAudio(const float* input, int input_frames, int input_rate,
                                       float* output, int output_frames, int output_rate) {
    if (!input || !output || input_frames == 0 || output_frames == 0 || input_rate == 0 || output_rate == 0) {
        return;
    }
    
    // If rates are the same, just copy
    if (input_rate == output_rate) {
        int copy_frames = (input_frames < output_frames) ? input_frames : output_frames;
        std::copy(input, input + copy_frames, output);
        return;
    }
    
    // Calculate the ratio between input and output sample rates
    double ratio = static_cast<double>(input_rate) / static_cast<double>(output_rate);
    
    // Debug: Show resampling calculation
    static int debug_resample_counter = 0;

    debug_resample_counter++;
    
    // Resample using linear interpolation
    for (int i = 0; i < output_frames; ++i) {
        double source_index = static_cast<double>(i) * ratio;
        int index0 = static_cast<int>(source_index);
        int index1 = index0 + 1;
        
        if (index0 >= input_frames) {
            output[i] = 0.0f;
            continue;
        }
        
        if (index1 >= input_frames) {
            output[i] = input[index0];
        } else {
            // Linear interpolation
            double fraction = source_index - static_cast<double>(index0);
            output[i] = static_cast<float>(
                (1.0 - fraction) * input[index0] + fraction * input[index1]
            );
        }
    }
}

void WindowsAudioCapture::SendAudioFormat() {
    if (!method_channel_) return;

    flutter::EncodableMap format_map;
    format_map[flutter::EncodableValue("sampleRate")] = flutter::EncodableValue(static_cast<double>(FLUTTER_SAMPLE_RATE));
    format_map[flutter::EncodableValue("channels")] = flutter::EncodableValue(FLUTTER_CHANNELS);
    format_map[flutter::EncodableValue("bitsPerChannel")] = flutter::EncodableValue(FLUTTER_BITS_PER_SAMPLE);
    format_map[flutter::EncodableValue("isFloat")] = flutter::EncodableValue(false);
    format_map[flutter::EncodableValue("isBigEndian")] = flutter::EncodableValue(false);
    format_map[flutter::EncodableValue("isInterleaved")] = flutter::EncodableValue(true);

    method_channel_->InvokeMethod("audioFormat", std::make_unique<flutter::EncodableValue>(format_map));
}

void WindowsAudioCapture::SendAudioData(const std::vector<uint8_t>& data) {
    if (!method_channel_ || data.empty()) return;

    method_channel_->InvokeMethod("audioFrame", std::make_unique<flutter::EncodableValue>(data));
}

void WindowsAudioCapture::SendError(const std::string& error_type, const std::string& message) {
    if (!method_channel_) return;

    method_channel_->InvokeMethod(error_type, std::make_unique<flutter::EncodableValue>(message));
}

std::string WindowsAudioCapture::CheckMicrophonePermission() {
    // On Windows, microphone permission is handled at the system level
    // We can try to create a microphone device to check if it's accessible
    try {
        IMMDeviceEnumerator* temp_enumerator = nullptr;
        HRESULT hr = CoCreateInstance(CLSID_MMDeviceEnumerator, nullptr, CLSCTX_ALL,
                                     IID_IMMDeviceEnumerator, (void**)&temp_enumerator);
        if (FAILED(hr)) return "denied";
        
        IMMDevice* temp_device = nullptr;
        hr = temp_enumerator->GetDefaultAudioEndpoint(eCapture, eConsole, &temp_device);
        
        SafeRelease((IUnknown**)&temp_device);
        SafeRelease((IUnknown**)&temp_enumerator);
        
        return SUCCEEDED(hr) ? "granted" : "denied";
    } catch (...) {
        return "denied";
    }
}

bool WindowsAudioCapture::RequestMicrophonePermission() {
    // On Windows, permission is granted implicitly when accessing the device
    // Return true if we can access the microphone
    return CheckMicrophonePermission() == "granted";
}

std::string WindowsAudioCapture::CheckScreenCapturePermission() {
    // Screen capture permission is always granted on Windows for loopback audio
    return "granted";
}

bool WindowsAudioCapture::RequestScreenCapturePermission() {
    // Always granted on Windows
    return true;
}

void WindowsAudioCapture::SetMethodChannel(std::shared_ptr<flutter::MethodChannel<flutter::EncodableValue>> channel) {
    method_channel_ = channel;
}

void WindowsAudioCapture::Cleanup() {
    StopCapture();

    SafeRelease((IUnknown**)&microphone_capture_);
    SafeRelease((IUnknown**)&loopback_capture_);
    SafeRelease((IUnknown**)&microphone_client_);
    SafeRelease((IUnknown**)&loopback_client_);
    SafeRelease((IUnknown**)&microphone_device_);
    SafeRelease((IUnknown**)&loopback_device_);
    SafeRelease((IUnknown**)&device_enumerator_);

    if (microphone_format_) {
        CoTaskMemFree(microphone_format_);
        microphone_format_ = nullptr;
    }
    if (loopback_format_) {
        CoTaskMemFree(loopback_format_);
        loopback_format_ = nullptr;
    }
    if (output_format_) {
        CoTaskMemFree(output_format_);
        output_format_ = nullptr;
    }
    
    // Clear accumulation buffers
    mic_accumulator_.clear();
    system_accumulator_.clear();
}

std::string WindowsAudioCapture::HResultToString(HRESULT hr) {
    _com_error err(hr);
    std::wstring message = err.ErrorMessage();
    
    // Convert wide string to multi-byte string using Windows API
    if (message.empty()) {
        return std::string();
    }
    
    int size_needed = WideCharToMultiByte(CP_UTF8, 0, message.c_str(), -1, nullptr, 0, nullptr, nullptr);
    if (size_needed <= 0) {
        return "Unknown error";
    }
    
    std::string result(size_needed - 1, 0); // -1 to exclude null terminator
    WideCharToMultiByte(CP_UTF8, 0, message.c_str(), -1, &result[0], size_needed, nullptr, nullptr);
    
    return result;
}

void WindowsAudioCapture::SafeRelease(IUnknown** ppunk) {
    if (*ppunk) {
        (*ppunk)->Release();
        *ppunk = nullptr;
    }
}

bool WindowsAudioCapture::DetectDeviceChanges() {
    // Check if the current default devices have changed
    // This is simpler and more reliable than searching for "preferred" devices
    
    // Check if default microphone device changed
    IMMDevice* current_default_mic = nullptr;
    HRESULT hr = device_enumerator_->GetDefaultAudioEndpoint(eCapture, eConsole, &current_default_mic);
    if (FAILED(hr)) return false;
    
    LPWSTR current_default_mic_id = nullptr;
    current_default_mic->GetId(&current_default_mic_id);
    
    LPWSTR current_mic_id = nullptr;
    microphone_device_->GetId(&current_mic_id);
    
    bool mic_changed = wcscmp(current_default_mic_id, current_mic_id) != 0;
    
    CoTaskMemFree(current_default_mic_id);
    CoTaskMemFree(current_mic_id);
    current_default_mic->Release();
    
    // Check if default render device changed
    IMMDevice* current_default_render = nullptr;
    hr = device_enumerator_->GetDefaultAudioEndpoint(eRender, eConsole, &current_default_render);
    if (FAILED(hr)) return mic_changed; // Return mic change status even if render check fails
    
    LPWSTR current_default_render_id = nullptr;
    current_default_render->GetId(&current_default_render_id);
    
    LPWSTR current_render_id = nullptr;
    loopback_device_->GetId(&current_render_id);
    
    bool render_changed = wcscmp(current_default_render_id, current_render_id) != 0;
    
    CoTaskMemFree(current_default_render_id);
    CoTaskMemFree(current_render_id);
    current_default_render->Release();
    
    if (mic_changed || render_changed) {
        std::cout << "DEVICE DETECTION: Default device changed - Mic: " << (mic_changed ? "YES" : "NO") 
                  << ", Render: " << (render_changed ? "YES" : "NO") << std::endl;
    }
    
    return mic_changed || render_changed;
}

bool WindowsAudioCapture::RecoverFromDeviceChange() {
    std::cout << "RECOVERY: Starting device recovery process..." << std::endl;
    
    // Stop current clients (but don't change is_capturing_ state)
    if (microphone_client_) {
        microphone_client_->Stop();
    }
    if (loopback_client_) {
        loopback_client_->Stop();
    }
    
    // Clean up current audio clients and devices
    CleanupAudioClients();
    
    // Try to reinitialize with new preferred devices
    if (!ReinitializeAudioDevices()) {
        std::cout << "RECOVERY: Failed to reinitialize devices" << std::endl;
        return false;
    }
    
    // Restart clients
    HRESULT hr = microphone_client_->Start();
    if (FAILED(hr)) {
        std::cout << "RECOVERY: Failed to restart microphone client: " << HResultToString(hr) << std::endl;
        return false;
    }
    
    hr = loopback_client_->Start();
    if (FAILED(hr)) {
        std::cout << "RECOVERY: Failed to restart loopback client: " << HResultToString(hr) << std::endl;
        microphone_client_->Stop();
        return false;
    }
    
    std::cout << "RECOVERY: Device recovery completed successfully!" << std::endl;
    return true;
}

bool WindowsAudioCapture::ReinitializeAudioDevices() {
    std::cout << "RECOVERY: Reinitializing audio devices..." << std::endl;
    
    // Reinitialize microphone
    if (!InitializeMicrophone()) {
        std::cout << "RECOVERY: Failed to reinitialize microphone" << std::endl;
        return false;
    }
    
    // Reinitialize loopback
    if (!InitializeLoopback()) {
        std::cout << "RECOVERY: Failed to reinitialize loopback" << std::endl;
        return false;
    }
    
    std::cout << "RECOVERY: Audio devices reinitialized successfully" << std::endl;
    return true;
}

void WindowsAudioCapture::CleanupAudioClients() {
    std::cout << "RECOVERY: Cleaning up audio clients..." << std::endl;
    
    SafeRelease((IUnknown**)&microphone_capture_);
    SafeRelease((IUnknown**)&loopback_capture_);
    SafeRelease((IUnknown**)&microphone_client_);
    SafeRelease((IUnknown**)&loopback_client_);
    SafeRelease((IUnknown**)&microphone_device_);
    SafeRelease((IUnknown**)&loopback_device_);
    
    if (microphone_format_) {
        CoTaskMemFree(microphone_format_);
        microphone_format_ = nullptr;
    }
    if (loopback_format_) {
        CoTaskMemFree(loopback_format_);
        loopback_format_ = nullptr;
    }
}

std::string WindowsAudioCapture::CheckLocationPermission() {
    try {
        // Check if location services are enabled system-wide
        HKEY hKey;
        LONG result = RegOpenKeyEx(HKEY_LOCAL_MACHINE,
            L"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\location",
            0, KEY_READ, &hKey);
        
        if (result != ERROR_SUCCESS) {
            return "denied";
        }
        
        // Read the Value as a string
        wchar_t stringValue[256] = {0};
        DWORD dataSize = sizeof(stringValue);
        DWORD valueType = 0;
        
        result = RegQueryValueExW(hKey, L"Value", NULL, &valueType, (LPBYTE)stringValue, &dataSize);
        RegCloseKey(hKey);
        
        if (result != ERROR_SUCCESS) {
            return "denied";
        }
        
        // Check the string value
        std::wstring valueStr(stringValue);
        if (valueStr == L"Allow") {
            return "granted";
        } else if (valueStr == L"Deny") {
            return "denied";
        } else {
            // If value is not explicitly "Allow", consider it denied
            return "denied";
        }
        
    } catch (...) {
        return "denied";
    }
}

bool WindowsAudioCapture::RequestLocationPermission() {
    try {
        // On Windows, we need to direct the user to open system settings
        // since there's no direct API to request location permission programmatically
        // for desktop apps like there is for UWP apps
        
        // First check if it's already granted
        std::string currentStatus = CheckLocationPermission();
        if (currentStatus == "granted") {
            return true;
        }
        
        // Open Windows Settings to Privacy & Security > Location
        std::wstring settingsUri = L"ms-settings:privacy-location";
        
        HINSTANCE result = ShellExecute(
            NULL,           // parent window handle
            L"open",        // operation
            settingsUri.c_str(),  // file/URI to open
            NULL,           // parameters
            NULL,           // default directory
            SW_SHOWNORMAL   // show command
        );
        
        // ShellExecute returns a value greater than 32 on success
        if ((INT_PTR)result > 32) {
            // We opened settings successfully, but we can't know if user actually granted permission
            // Return false to indicate that user intervention is needed
            return false;
        } else {
            return false;
        }
        
    } catch (...) {
        return false;
    }
}

std::string WindowsAudioCapture::CheckNotificationPermission() {
    try {
        // Check if notifications are enabled system-wide
        HKEY hKey;
        LONG result;
        
        // Check if notifications are disabled globally
        result = RegOpenKeyEx(HKEY_CURRENT_USER,
            L"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Notifications\\Settings",
            0, KEY_READ, &hKey);
        
        if (result == ERROR_SUCCESS) {
            // Check if notifications are disabled globally
            DWORD dataSize = sizeof(DWORD);
            DWORD value = 1; // Default to enabled
            RegQueryValueEx(hKey, L"NOC_GLOBAL_SETTING_ALLOW_NOTIFICATION_SOUND", NULL, NULL, (LPBYTE)&value, &dataSize);
            
            RegCloseKey(hKey);
            
            // If global notifications are explicitly disabled (value == 0), return denied
            if (value == 0) {
                return "denied";
            }
        }
        
        // For Windows desktop applications (Win32 apps), notifications are typically 
        // allowed by default unless the user has specifically disabled them.
        // Unlike mobile platforms, Windows doesn't require explicit permission request
        // for desktop applications to show notifications.
        return "granted";
        
    } catch (...) {
        // If we can't check the registry, assume notifications are allowed
        // This is the safe default for Windows desktop applications
        return "granted";
    }
}

bool WindowsAudioCapture::RequestNotificationPermission() {
    try {
        // Check if notifications are already granted
        std::string currentStatus = CheckNotificationPermission();
        if (currentStatus == "granted") {
            return true;
        }
        
        // On Windows desktop applications, notifications don't require explicit permission
        // like mobile platforms do. If we reach here, it means notifications are disabled
        // system-wide, so we direct the user to settings to enable them.
        
        // Open Windows Settings to System > Notifications
        std::wstring settingsUri = L"ms-settings:notifications";
        
        HINSTANCE result = ShellExecute(
            NULL,           // parent window handle
            L"open",        // operation
            settingsUri.c_str(),  // file/URI to open
            NULL,           // parameters
            NULL,           // default directory
            SW_SHOWNORMAL   // show command
        );
        
        // ShellExecute returns a value greater than 32 on success
        if ((INT_PTR)result > 32) {
            // We opened settings successfully
            // For Windows desktop apps, we assume permission will be granted
            // once the user enables notifications system-wide
            return true;
        } else {
            return false;
        }
        
    } catch (...) {
        return false;
    }
} 