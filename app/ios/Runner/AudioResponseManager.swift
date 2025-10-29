import AVFoundation
import Flutter

class AudioResponseManager: NSObject, AVAudioPlayerDelegate {
    static let shared = AudioResponseManager()
    
    private var audioPlayer: AVAudioPlayer?
    private var audioSession: AVAudioSession = AVAudioSession.sharedInstance()
    private var isPlaying: Bool = false
    private var completionHandler: (() -> Void)?
    private var messageQueue: [(audioData: Data, completion: (() -> Void)?)] = []
    
    private override init() {
        super.init()
        // Pre-configure audio session on init so it's ready for background use
        configureAudioSessionForBackground()
    }
    
    // Pre-activate audio session to enable background playback
    private func configureAudioSessionForBackground() {
        do {
            // Configure for playback in background with BLE coexistence
            try audioSession.setCategory(
                .playback,
                mode: .spokenAudio,
                options: [.mixWithOthers, .allowBluetooth, .allowBluetoothA2DP]
            )
            // Don't activate yet - just configure
            print("AudioResponseManager: ✅ Audio session pre-configured for background playback")
        } catch {
            print("AudioResponseManager: ⚠️ Failed to pre-configure audio session: \(error)")
        }
    }
    
    // Public method to activate audio session (call when BLE connects)
    func activateAudioSession() {
        do {
            try audioSession.setActive(true)
            print("AudioResponseManager: ✅ Audio session activated")
        } catch {
            print("AudioResponseManager: ⚠️ Failed to activate audio session: \(error)")
        }
    }
    
    // Check if headphones are connected
    func isHeadphonesConnected() -> Bool {
        let route = audioSession.currentRoute
        
        print("AudioResponseManager: Checking audio outputs...")
        print("AudioResponseManager: Total outputs: \(route.outputs.count)")
        
        for output in route.outputs {
            print("AudioResponseManager: Output - Name: '\(output.portName)', Type: \(output.portType.rawValue), UID: '\(output.uid)'")
            
            switch output.portType {
            case .headphones:
                print("AudioResponseManager: ✅ Found wired headphones")
                return true
            case .bluetoothA2DP:
                print("AudioResponseManager: ✅ Found Bluetooth A2DP (AirPods/headphones)")
                return true
            case .bluetoothHFP:
                print("AudioResponseManager: ✅ Found Bluetooth HFP")
                return true
            case .bluetoothLE:
                print("AudioResponseManager: ✅ Found Bluetooth LE")
                return true
            case .airPlay:
                print("AudioResponseManager: ✅ Found AirPlay")
                return true
            default:
                print("AudioResponseManager: ❌ Not a headphone output: \(output.portType.rawValue)")
                break
            }
        }
        
        print("AudioResponseManager: ❌ No headphones found")
        return false
    }
    
    // Play audio bytes through headphones (MP3 from OpenAI TTS)
    func playAudioBytes(audioData: Data, completion: (() -> Void)? = nil) {
        // Only play if headphones are connected
        guard isHeadphonesConnected() else {
            print("AudioResponseManager: No headphones connected, skipping playback")
            completion?()
            return
        }
        
        print("AudioResponseManager: Received \(audioData.count) bytes of audio data")
        
        // If already playing, queue this audio
        if isPlaying {
            print("AudioResponseManager: Already playing, adding to queue (queue size: \(messageQueue.count + 1))")
            messageQueue.append((audioData: audioData, completion: completion))
            return
        }
        
        // Start playing immediately
        isPlaying = true
        completionHandler = completion
        startPlayback(audioData: audioData)
    }
    
    private func startPlayback(audioData: Data) {
        print("AudioResponseManager: Current audio session category: \(audioSession.category.rawValue)")
        print("AudioResponseManager: Current audio session mode: \(audioSession.mode.rawValue)")
        print("AudioResponseManager: Audio session active: \(audioSession.secondaryAudioShouldBeSilencedHint)")
        
        // Ensure audio session is configured and active
        let currentCategory = audioSession.category
        
        // Always ensure session is properly configured for playback
        if currentCategory != .playback && currentCategory != .playAndRecord {
            print("AudioResponseManager: Current category (\(currentCategory.rawValue)) not suitable, updating...")
            do {
                try audioSession.setCategory(
                    .playback,
                    mode: .spokenAudio,
                    options: [.mixWithOthers, .allowBluetooth, .allowBluetoothA2DP]
                )
                print("AudioResponseManager: ✅ Audio session category updated")
            } catch {
                print("AudioResponseManager: ⚠️ Could not update category: \(error)")
            }
        }
        
        // Ensure session is active (critical for background playback)
        do {
            try audioSession.setActive(true)
            print("AudioResponseManager: ✅ Audio session activated")
        } catch {
            print("AudioResponseManager: ⚠️ Could not activate session: \(error) - trying playback anyway")
        }
        
        // Create AVAudioPlayer from audio data
        do {
            audioPlayer = try AVAudioPlayer(data: audioData)
            audioPlayer?.delegate = self
            audioPlayer?.prepareToPlay() // Prepare before playing
            
            print("AudioResponseManager: Audio player created, duration: \(audioPlayer?.duration ?? 0)s")
            print("AudioResponseManager: Starting audio playback...")
            
            let success = audioPlayer?.play() ?? false
            if success {
                print("AudioResponseManager: ✅ Audio playback started")
            } else {
                print("AudioResponseManager: ❌ Failed to start audio playback")
                print("AudioResponseManager: Player state - isPlaying: \(audioPlayer?.isPlaying ?? false), duration: \(audioPlayer?.duration ?? 0)")
                cleanup()
            }
        } catch {
            print("AudioResponseManager: ❌ Failed to create audio player: \(error)")
            cleanup()
        }
    }
    
    // Stop current playback
    func stopPlayback() {
        if isPlaying {
            audioPlayer?.stop()
            cleanup()
        }
    }
    
    // Clear the message queue
    func clearQueue() {
        print("AudioResponseManager: Clearing queue (\(messageQueue.count) messages)")
        messageQueue.removeAll()
    }
    
    private func cleanup() {
        print("AudioResponseManager: Cleaning up after audio playback")
        
        // Call completion handler for current message
        completionHandler?()
        completionHandler = nil
        
        audioPlayer = nil
        isPlaying = false
        
        // DON'T deactivate audio session - keep it active for:
        // 1. Background audio to continue when app is closed
        // 2. BLE audio to continue working
        print("AudioResponseManager: Keeping audio session active for background playback")
        
        // Process next message in queue
        if !messageQueue.isEmpty {
            let next = messageQueue.removeFirst()
            print("AudioResponseManager: Playing next queued audio (remaining in queue: \(messageQueue.count))")
            isPlaying = true
            completionHandler = next.completion
            startPlayback(audioData: next.audioData)
        } else {
            print("AudioResponseManager: Queue empty, audio player idle")
        }
    }
    
    // MARK: - AVAudioPlayerDelegate
    
    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        print("AudioResponseManager: Audio finished playing, success: \(flag)")
        cleanup()
    }
    
    func audioPlayerDecodeErrorDidOccur(_ player: AVAudioPlayer, error: Error?) {
        print("AudioResponseManager: Audio decode error: \(error?.localizedDescription ?? "unknown")")
        cleanup()
    }
}

