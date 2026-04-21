//! macOS system audio capture via Core Audio Taps (macOS 14.4+).
//!
//! Ported from `desktop/Desktop/Sources/SystemAudioCaptureService.swift`.
//!
//! Flow:
//! 1. Create a `CATapDescription` (ObjC class) configured for stereo global tap.
//! 2. `AudioHardwareCreateProcessTap` → tap id.
//! 3. `AudioHardwareCreateAggregateDevice` with the tap in its sub-device list.
//! 4. `AudioDeviceCreateIOProcIDWithBlock` registers a real-time audio callback.
//! 5. `AudioDeviceStart` begins delivering interleaved f32 frames at the
//!    device's native rate (typically 44.1 or 48 kHz).
//! 6. In the callback we downmix to mono, linearly resample to 16 kHz, and
//!    forward i16 chunks via a bounded tokio mpsc.
//!
//! All HAL calls are synchronous IPC to `coreaudiod` and can block for
//! seconds after wake — teardown runs on a detached thread via `Drop`.

#![cfg(target_os = "macos")]

use std::ffi::c_void;
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::Arc;

use block2::{Block, RcBlock};
use core_foundation::base::{CFType, TCFType};
use core_foundation::boolean::CFBoolean;
use core_foundation::dictionary::CFDictionary;
use core_foundation::string::CFString;
use coreaudio_sys::{
    kAudioAggregateDeviceIsPrivateKey, kAudioAggregateDeviceNameKey,
    kAudioAggregateDeviceTapAutoStartKey, kAudioAggregateDeviceTapListKey,
    kAudioAggregateDeviceUIDKey, kAudioDevicePropertyScopeInput,
    kAudioDevicePropertyStreamFormat, kAudioObjectPropertyElementMain, kAudioObjectUnknown,
    kAudioSubTapUIDKey, noErr, AudioBufferList, AudioDeviceCreateIOProcIDWithBlock,
    AudioDeviceDestroyIOProcID, AudioDeviceIOProcID, AudioDeviceStart, AudioDeviceStop,
    AudioHardwareCreateAggregateDevice, AudioHardwareCreateProcessTap,
    AudioHardwareDestroyAggregateDevice, AudioHardwareDestroyProcessTap, AudioObjectGetPropertyData,
    AudioObjectID, AudioObjectPropertyAddress, AudioStreamBasicDescription, AudioTimeStamp,
    OSStatus,
};
use objc2::rc::Retained;
use objc2::runtime::NSObject;
use objc2::{extern_class, msg_send_id, ClassType};
use objc2_foundation::{NSArray, NSString, NSUUID};
use tokio::sync::mpsc;

// ---------------------------------------------------------------------------
// CATapDescription ObjC binding
// ---------------------------------------------------------------------------

extern_class!(
    #[derive(Debug, PartialEq, Eq, Hash)]
    pub struct CATapDescription;

    unsafe impl ClassType for CATapDescription {
        type Super = NSObject;
        type Mutability = objc2::mutability::InteriorMutable;
        const NAME: &'static str = "CATapDescription";
    }
);

// `muteBehavior` values for CATapDescription (macOS 14.4+ headers).
// 0 = unmuted — don't alter playback. This is what we want.
const CA_TAP_MUTE_BEHAVIOR_UNMUTED: i32 = 0;

impl CATapDescription {
    /// Initialize with `-initStereoGlobalTapButExcludeProcesses:` — a stereo
    /// tap that captures all system output except the listed process PIDs.
    /// Pass an empty array to capture everything.
    fn new_stereo_global(exclude_pids: &NSArray<NSObject>) -> Retained<Self> {
        unsafe {
            let this: Option<Retained<Self>> = msg_send_id![Self::class(), alloc];
            let this = this.expect("alloc CATapDescription");
            msg_send_id![this, initStereoGlobalTapButExcludeProcesses: exclude_pids]
        }
    }

    fn set_uuid(&self, uuid: &NSUUID) {
        unsafe {
            let _: () = objc2::msg_send![self, setUUID: uuid];
        }
    }

    fn set_name(&self, name: &NSString) {
        unsafe {
            let _: () = objc2::msg_send![self, setName: name];
        }
    }

    fn set_mute_behavior(&self, behavior: i32) {
        unsafe {
            let _: () = objc2::msg_send![self, setMuteBehavior: behavior];
        }
    }
}

// ---------------------------------------------------------------------------
// Shared state delivered to the real-time callback
// ---------------------------------------------------------------------------

/// State shared between the Rust-owned `SystemAudioCapture` and the block
/// registered with Core Audio. The block captures an `Arc<CallbackState>`.
struct CallbackState {
    is_running: AtomicBool,
    /// Source sample rate (set once after we read the device format).
    source_sample_rate: AtomicU32,
    /// Source channel count (1 or 2 typical).
    source_channels: AtomicU32,
    tx: mpsc::Sender<Vec<i16>>,
    /// Fractional-sample read position into the source stream — for linear
    /// resampling. Uses a single atomic-ish u64 (packed high=int, low=frac).
    /// Real-time callback runs on one thread, but we still read/write this
    /// from a single thread so a simple UnsafeCell-ish pattern via atomic
    /// is fine. We store it as two u32s: integer index, fractional numerator
    /// over 1<<24.
    resample_frac: std::sync::atomic::AtomicU32,
    /// Residual mono f32 samples from the previous callback, held across
    /// callbacks for the resampler to interpolate between boundaries.
    /// The callback is always invoked from the same HAL thread, so plain
    /// interior mutability behind a mutex is fine (we never contend).
    leftover: std::sync::Mutex<Vec<f32>>,
}

/// Fractional scale for the resampler (avoid floating-point drift).
const FRAC_SCALE: u64 = 1 << 24;

// ---------------------------------------------------------------------------
// Public capture type
// ---------------------------------------------------------------------------

pub struct SystemAudioCapture {
    tap_id: AudioObjectID,
    agg_dev_id: AudioObjectID,
    io_proc_id: AudioDeviceIOProcID,
    state: Arc<CallbackState>,
    /// Keep the block alive — Core Audio retains it but we also need to
    /// ensure the captured Arc doesn't drop early.
    _block: RcBlock<dyn Fn(*const AudioTimeStamp, *const AudioBufferList, *const AudioTimeStamp, *mut AudioBufferList, *const AudioTimeStamp)>,
}

impl SystemAudioCapture {
    /// Start capturing system audio. Feeds mono 16 kHz i16 chunks to `tx`.
    pub fn start(tx: mpsc::Sender<Vec<i16>>) -> Result<Self, String> {
        // 1. Build the tap description (ObjC).
        let exclude: Retained<NSArray<NSObject>> = NSArray::new();
        let desc = CATapDescription::new_stereo_global(&exclude);
        let uuid = NSUUID::new();
        desc.set_uuid(&uuid);
        let name = NSString::from_str("Nooto System Audio Tap");
        desc.set_name(&name);
        desc.set_mute_behavior(CA_TAP_MUTE_BEHAVIOR_UNMUTED);

        // 2. Create the process tap.
        let mut tap_id: AudioObjectID = kAudioObjectUnknown;
        let status: OSStatus = unsafe {
            AudioHardwareCreateProcessTap(
                Retained::as_ptr(&desc) as *mut _,
                &mut tap_id,
            )
        };
        if status != noErr as OSStatus {
            return Err(format!("AudioHardwareCreateProcessTap failed: {}", status));
        }

        // 3. Build the aggregate-device description dictionary.
        let uuid_cf = CFString::new(&uuid.UUIDString().to_string());
        let agg_uid = CFString::new(&format!("nooto.systemaudio.{}", uuid.UUIDString()));
        let agg_name = CFString::new("Nooto System Audio Tap Device");

        let sub_tap_key = unsafe { cfstring_from_static(kAudioSubTapUIDKey) };
        let sub_tap_dict = CFDictionary::from_CFType_pairs(&[(
            sub_tap_key.as_CFType(),
            uuid_cf.as_CFType(),
        )]);

        let tap_list = cf_array_of_dicts(&[sub_tap_dict]);

        let name_key = unsafe { cfstring_from_static(kAudioAggregateDeviceNameKey) };
        let uid_key = unsafe { cfstring_from_static(kAudioAggregateDeviceUIDKey) };
        let private_key = unsafe { cfstring_from_static(kAudioAggregateDeviceIsPrivateKey) };
        let taplist_key = unsafe { cfstring_from_static(kAudioAggregateDeviceTapListKey) };
        let autostart_key = unsafe { cfstring_from_static(kAudioAggregateDeviceTapAutoStartKey) };

        let agg_desc = CFDictionary::from_CFType_pairs(&[
            (name_key.as_CFType(), agg_name.as_CFType()),
            (uid_key.as_CFType(), agg_uid.as_CFType()),
            (private_key.as_CFType(), CFBoolean::true_value().as_CFType()),
            (taplist_key.as_CFType(), tap_list.as_CFType()),
            (autostart_key.as_CFType(), CFBoolean::true_value().as_CFType()),
        ]);

        let mut agg_dev_id: AudioObjectID = kAudioObjectUnknown;
        let status: OSStatus = unsafe {
            AudioHardwareCreateAggregateDevice(
                agg_desc.as_concrete_TypeRef() as _,
                &mut agg_dev_id,
            )
        };
        if status != noErr as OSStatus {
            unsafe { AudioHardwareDestroyProcessTap(tap_id) };
            return Err(format!(
                "AudioHardwareCreateAggregateDevice failed: {}",
                status
            ));
        }

        // 4. Read the stream format so we know source rate/channels.
        let format = match read_stream_format(agg_dev_id) {
            Some(f) => f,
            None => {
                unsafe {
                    AudioHardwareDestroyAggregateDevice(agg_dev_id);
                    AudioHardwareDestroyProcessTap(tap_id);
                }
                return Err("Failed to read aggregate device stream format".into());
            }
        };
        tracing::info!(
            "[sys-audio] source format: {} Hz, {} ch, {} bits",
            format.mSampleRate,
            format.mChannelsPerFrame,
            format.mBitsPerChannel
        );

        let state = Arc::new(CallbackState {
            is_running: AtomicBool::new(true),
            source_sample_rate: AtomicU32::new(format.mSampleRate as u32),
            source_channels: AtomicU32::new(format.mChannelsPerFrame),
            tx,
            resample_frac: std::sync::atomic::AtomicU32::new(0),
            leftover: std::sync::Mutex::new(Vec::with_capacity(8192)),
        });

        // 5. Build the IOProc block. Core Audio retains it; we also keep an
        //    RcBlock around to guarantee the Arc clone stays alive.
        let cb_state = state.clone();
        let block = RcBlock::new(move |_in_now: *const AudioTimeStamp,
                                       in_input_data: *const AudioBufferList,
                                       _in_input_time: *const AudioTimeStamp,
                                       _out_output_data: *mut AudioBufferList,
                                       _in_output_time: *const AudioTimeStamp| {
            if !cb_state.is_running.load(Ordering::Acquire) {
                return;
            }
            unsafe {
                handle_audio_input(&cb_state, in_input_data);
            }
        });

        // 6. Register the IO proc.
        let mut io_proc_id: AudioDeviceIOProcID = std::ptr::null_mut();
        let status: OSStatus = unsafe {
            AudioDeviceCreateIOProcIDWithBlock(
                &mut io_proc_id,
                agg_dev_id,
                std::ptr::null_mut(),
                // block2 RcBlock derefs to the raw block pointer via &*block.
                &*block as *const Block<_> as *mut c_void,
            )
        };
        if status != noErr as OSStatus || io_proc_id.is_null() {
            unsafe {
                AudioHardwareDestroyAggregateDevice(agg_dev_id);
                AudioHardwareDestroyProcessTap(tap_id);
            }
            return Err(format!(
                "AudioDeviceCreateIOProcIDWithBlock failed: {}",
                status
            ));
        }

        // 7. Start the aggregate device.
        let status: OSStatus = unsafe { AudioDeviceStart(agg_dev_id, io_proc_id) };
        if status != noErr as OSStatus {
            unsafe {
                AudioDeviceDestroyIOProcID(agg_dev_id, io_proc_id);
                AudioHardwareDestroyAggregateDevice(agg_dev_id);
                AudioHardwareDestroyProcessTap(tap_id);
            }
            return Err(format!("AudioDeviceStart failed: {}", status));
        }

        tracing::info!("[sys-audio] capture started (tap={}, agg={})", tap_id, agg_dev_id);

        Ok(Self {
            tap_id,
            agg_dev_id,
            io_proc_id,
            state,
            _block: block,
        })
    }
}

impl Drop for SystemAudioCapture {
    fn drop(&mut self) {
        self.state.is_running.store(false, Ordering::Release);
        let agg_dev_id = self.agg_dev_id;
        let tap_id = self.tap_id;
        let io_proc_id = self.io_proc_id;
        // HAL calls can block for seconds on wake-from-sleep. Detach teardown
        // to a background thread so Drop returns fast.
        std::thread::spawn(move || unsafe {
            if !io_proc_id.is_null() && agg_dev_id != kAudioObjectUnknown {
                AudioDeviceStop(agg_dev_id, io_proc_id);
                AudioDeviceDestroyIOProcID(agg_dev_id, io_proc_id);
            }
            if agg_dev_id != kAudioObjectUnknown {
                AudioHardwareDestroyAggregateDevice(agg_dev_id);
            }
            if tap_id != kAudioObjectUnknown {
                AudioHardwareDestroyProcessTap(tap_id);
            }
            tracing::info!("[sys-audio] teardown complete");
        });
    }
}

// ---------------------------------------------------------------------------
// Real-time audio handling (runs on a HAL-owned thread)
// ---------------------------------------------------------------------------

const TARGET_RATE: u32 = 16_000;
/// Minimum samples we accumulate before sending a chunk. At 16 kHz this is
/// ~10 ms which matches the cpal mic path.
const MIN_CHUNK_SAMPLES: usize = 160;

unsafe fn handle_audio_input(state: &CallbackState, input: *const AudioBufferList) {
    if input.is_null() {
        return;
    }
    let bufs = &*input;
    if bufs.mNumberBuffers == 0 {
        return;
    }
    let buf = &bufs.mBuffers[0];
    if buf.mData.is_null() || buf.mDataByteSize == 0 {
        return;
    }

    let channels = state.source_channels.load(Ordering::Relaxed).max(1);
    let source_rate = state.source_sample_rate.load(Ordering::Relaxed);
    if source_rate == 0 {
        return;
    }

    let bytes_per_frame = 4 * channels as u32; // f32 * ch
    let frame_count = buf.mDataByteSize / bytes_per_frame;
    if frame_count == 0 {
        return;
    }

    // Downmix to mono f32 and prepend the single-sample tail from the
    // previous callback so linear interpolation is continuous across the
    // callback boundary.
    let src = std::slice::from_raw_parts(
        buf.mData as *const f32,
        (frame_count * channels) as usize,
    );
    let mut leftover = state.leftover.lock().unwrap_or_else(|e| e.into_inner());
    // Keep any unconsumed tail from the previous callback so linear
    // interpolation is continuous across the boundary.
    leftover.reserve(frame_count as usize);
    if channels >= 2 {
        for i in 0..frame_count as usize {
            let base = i * channels as usize;
            let l = src[base];
            let r = src[base + 1];
            leftover.push((l + r) * 0.5);
        }
    } else {
        leftover.extend_from_slice(src);
    }

    // Fixed-point linear resample. `step_fp` is source-samples per output
    // sample, in units of 1/FRAC_SCALE. `pos` indexes into `leftover` in
    // the same units, carried across callbacks via (resample_int,
    // resample_frac) so the phase is continuous.
    let step_fp = (source_rate as u64 * FRAC_SCALE) / TARGET_RATE as u64;
    // int counter is always 0 at the start of a callback — we drained
    // consumed samples from `leftover` at the end of the previous call, so
    // the next output sample lands between leftover[0] and leftover[1].
    // Only the fractional phase is carried across callbacks.
    let frac_init = state.resample_frac.load(Ordering::Relaxed) as u64;
    let mono = &leftover[..];
    let mut pos: u64 = frac_init;

    let mut out: Vec<i16> =
        Vec::with_capacity((frame_count as usize * TARGET_RATE as usize) / source_rate as usize + 4);

    loop {
        let idx = (pos >> 24) as usize;
        if idx + 1 >= mono.len() {
            break;
        }
        let frac = (pos & ((1u64 << 24) - 1)) as f32 / FRAC_SCALE as f32;
        let s0 = mono[idx];
        let s1 = mono[idx + 1];
        let interp = s0 + (s1 - s0) * frac;
        let clamped = interp.clamp(-1.0, 1.0);
        out.push((clamped * 32767.0) as i16);
        pos += step_fp;
    }

    // Advance. Drop fully-consumed samples from `leftover`, leaving the
    // sample at `consumed_int` as `mono[0]` for the next callback so
    // fractional-phase interpolation stays continuous.
    let consumed_int = (pos >> 24) as usize;
    let carry_frac = pos & ((1u64 << 24) - 1);
    let drain_to = consumed_int.min(mono.len());
    if drain_to > 0 {
        leftover.drain(..drain_to);
    }
    // Safety cap — keep at most a few hundred ms of backlog if something
    // went sideways.
    const LEFTOVER_CAP: usize = 4096;
    if leftover.len() > LEFTOVER_CAP {
        let excess = leftover.len() - LEFTOVER_CAP;
        leftover.drain(..excess);
    }
    state.resample_frac.store(carry_frac as u32, Ordering::Relaxed);

    if out.len() < MIN_CHUNK_SAMPLES {
        return;
    }

    // try_send — drop on full (consumer stalled).
    if let Err(mpsc::error::TrySendError::Full(_)) = state.tx.try_send(out) {
        // Silent drop — warning noise would flood the RT thread.
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn read_stream_format(device_id: AudioObjectID) -> Option<AudioStreamBasicDescription> {
    let address = AudioObjectPropertyAddress {
        mSelector: kAudioDevicePropertyStreamFormat,
        mScope: kAudioDevicePropertyScopeInput,
        mElement: kAudioObjectPropertyElementMain,
    };
    let mut format = AudioStreamBasicDescription {
        mSampleRate: 0.0,
        mFormatID: 0,
        mFormatFlags: 0,
        mBytesPerPacket: 0,
        mFramesPerPacket: 0,
        mBytesPerFrame: 0,
        mChannelsPerFrame: 0,
        mBitsPerChannel: 0,
        mReserved: 0,
    };
    let mut size = std::mem::size_of::<AudioStreamBasicDescription>() as u32;
    let status = unsafe {
        AudioObjectGetPropertyData(
            device_id,
            &address,
            0,
            std::ptr::null(),
            &mut size,
            &mut format as *mut _ as *mut c_void,
        )
    };
    if status == noErr as OSStatus {
        Some(format)
    } else {
        None
    }
}

/// Wrap a Core Audio `CFStringRef` constant (from coreaudio-sys) into an
/// owned `CFString`. These constants are static — no retain needed.
unsafe fn cfstring_from_static(cfstr: core_foundation_sys::string::CFStringRef) -> CFString {
    CFString::wrap_under_get_rule(cfstr)
}

fn cf_array_of_dicts(dicts: &[CFDictionary]) -> core_foundation::array::CFArray<CFDictionary> {
    use core_foundation::array::CFArray;
    CFArray::from_CFTypes(dicts)
}
