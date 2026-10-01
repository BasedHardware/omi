//! OmiSimulator — Crepuscularity (GPUI) desktop shell + local BLE peripheral.
//!
//! UI framework: https://crepuscularity.tsc.hk (tschk/crepuscularity)
//! BLE: local CoreBluetooth GATT peripheral via ble-peripheral-rust — NOT an HTTP API.

mod audio;
mod ble;

use std::sync::atomic::Ordering;
use std::sync::Arc;

use crepuscularity_gpui::prelude::*;
use gpui::{bounds, point, size, App, ClickEvent, WindowBounds};
use tokio::sync::mpsc;

use audio::AudioCapture;
use ble::{BleCommand, BleState};

struct OmiSimulatorView {
    state: BleState,
    cmd_tx: mpsc::UnboundedSender<BleCommand>,
    status_rx: tokio::sync::watch::Receiver<String>,
    audio: Arc<AudioCapture>,
    recording: bool,
    status_text: String,
}

impl OmiSimulatorView {
    fn new(cx: &mut Context<Self>) -> Self {
        let (state, status_rx) = BleState::new();
        let cmd_tx = ble::spawn_ble(state.clone());
        let audio = Arc::new(AudioCapture::new(cmd_tx.clone()));

        // Poll BLE status into the view periodically
        cx.spawn(async move |this, cx| {
            loop {
                cx.background_executor()
                    .timer(std::time::Duration::from_millis(250))
                    .await;
                let _ = this.update(cx, |view, cx| {
                    let next = view.status_rx.borrow().clone();
                    if next != view.status_text {
                        view.status_text = next;
                        cx.notify();
                    }
                    // Mirror LED/mic from BLE writes into UI refresh
                    cx.notify();
                });
            }
        })
        .detach();

        Self {
            state,
            cmd_tx,
            status_rx,
            audio,
            recording: false,
            status_text: "starting…".into(),
        }
    }

    fn battery_down(&mut self, _: &ClickEvent, _: &mut Window, cx: &mut Context<Self>) {
        let cur = self.state.battery.load(Ordering::Relaxed);
        let next = cur.saturating_sub(5);
        self.state.battery.store(next, Ordering::Relaxed);
        let _ = self.cmd_tx.send(BleCommand::SetBattery(next));
        cx.notify();
    }

    fn battery_up(&mut self, _: &ClickEvent, _: &mut Window, cx: &mut Context<Self>) {
        let cur = self.state.battery.load(Ordering::Relaxed);
        let next = (cur + 5).min(100);
        self.state.battery.store(next, Ordering::Relaxed);
        let _ = self.cmd_tx.send(BleCommand::SetBattery(next));
        cx.notify();
    }

    fn toggle_charging(&mut self, _: &ClickEvent, _: &mut Window, cx: &mut Context<Self>) {
        let next = !self.state.charging.load(Ordering::Relaxed);
        self.state.charging.store(next, Ordering::Relaxed);
        let _ = self.cmd_tx.send(BleCommand::SetCharging(next));
        cx.notify();
    }

    fn double_press(&mut self, _: &ClickEvent, _: &mut Window, _cx: &mut Context<Self>) {
        let _ = self.cmd_tx.send(BleCommand::FireDoublePress);
    }

    fn toggle_record(&mut self, _: &ClickEvent, _: &mut Window, cx: &mut Context<Self>) {
        self.recording = !self.recording;
        self.audio.set_recording(self.recording);
        cx.notify();
    }
}

impl Render for OmiSimulatorView {
    fn render(&mut self, _window: &mut Window, cx: &mut Context<Self>) -> impl IntoElement {
        let battery = self.state.battery.load(Ordering::Relaxed);
        let charging = self.state.charging.load(Ordering::Relaxed);
        let led = self.state.led.load(Ordering::Relaxed);
        let mic = self.state.mic_gain.load(Ordering::Relaxed);
        let advertising = self.state.advertising.load(Ordering::Relaxed);
        let recording = self.recording;
        let mic_ok = self.audio.available();
        let status = self.status_text.clone();
        let charge_label = if charging {
            "Charging: ON"
        } else {
            "Charging: OFF"
        };
        let record_label = if recording { "Stop" } else { "Record" };
        let adv_label = if advertising {
            "ADV: on"
        } else {
            "ADV: off"
        };
        let mic_note = if mic_ok {
            "mic: ready"
        } else {
            "mic: unavailable"
        };

        view! {r#"
            div w-full h-full bg-zinc-950 text-white flex flex-col p-6 gap-4 font-['Instrument_Sans']
                div flex flex-col gap-1
                    div text-2xl font-bold
                        "Omi simulator"
                    div text-sm text-zinc-400
                        "Advertising as Omi Devkit · Crepuscularity GPUI"
                    div text-xs text-cyan-400
                        "UI: https://crepuscularity.tsc.hk · BLE: local CoreBluetooth peripheral (no API base)"

                div h-px bg-zinc-800

                div flex items-center gap-3
                    div text-sm w-28
                        "Battery {battery}%"
                    button bg-zinc-800 hover:bg-zinc-700 px-3 py-1 rounded @click=battery_down
                        "−5"
                    button bg-zinc-800 hover:bg-zinc-700 px-3 py-1 rounded @click=battery_up
                        "+5"
                    div text-xs text-zinc-500
                        "{adv_label}"

                button bg-zinc-800 hover:bg-zinc-700 px-4 py-2 rounded w-fit @click=toggle_charging
                    "{charge_label}"

                div text-xs text-zinc-500
                    "LED {led} · Mic gain {mic} · {mic_note}"

                div flex gap-3
                    button bg-white text-black font-semibold px-4 py-2 rounded-lg hover:bg-zinc-200 @click=double_press
                        "Double press"
                    button bg-rose-600 text-white font-semibold px-4 py-2 rounded-lg hover:bg-rose-500 @click=toggle_record
                        "{record_label}"

                div text-xs text-zinc-500 mt-2
                    "Status: {status}"
        "#}
    }
}

fn main() {
    let _ = env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info"))
        .try_init();

    crepuscularity_gpui::application().run(|cx: &mut App| {
        use crepuscularity_gpui::prelude::*;
        let window_options = gpui_window_options(
            "com.basedhardware.OmiSimulator",
            "Omi Simulator",
            Some(WindowBounds::Windowed(bounds(
                point(px(120.), px(120.)),
                size(px(420.), px(360.)),
            ))),
            None,
        );

        match cx.open_window(window_options, |_win, cx| cx.new(OmiSimulatorView::new)) {
            Ok(_) => {}
            Err(e) => eprintln!("failed to open window: {e:?}"),
        }
    });
}
