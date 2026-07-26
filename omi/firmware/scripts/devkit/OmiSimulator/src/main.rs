use crepuscularity_gpui::{
    bounds, gpui_window_options, point, prelude::*, px, size, App, Application, ClickEvent,
    Context, Window,
};
use omi_product_emulator::core::{
    discover_bluetooth_targets, probe_device, set_bluetooth_connection, BluetoothTarget,
    ButtonEvent, FirmwareImage, FlashSession, PeripheralCatalog, Product,
};
use std::env;

struct EmulatorView {
    catalog: PeripheralCatalog,
    scan_generation: u64,
    scanning: bool,
    selected: Option<String>,
    dropdown_open: bool,
    status: String,
    image: Option<FirmwareImage>,
    flash: Option<FlashSession>,
}

impl EmulatorView {
    fn new(cx: &mut Context<Self>) -> Self {
        let image = env::var_os("OMI_EMULATOR_FIRMWARE")
            .and_then(|path| FirmwareImage::validate(path).ok());
        let mut view = Self {
            catalog: PeripheralCatalog::default(),
            scan_generation: 0,
            scanning: false,
            selected: None,
            dropdown_open: false,
            status: "Scanning for supported Bluetooth products".into(),
            image,
            flash: None,
        };
        view.start_scan(cx);
        view
    }

    fn toggle_targets(&mut self, _: &ClickEvent, _: &mut Window, cx: &mut Context<Self>) {
        self.dropdown_open = !self.dropdown_open;
        cx.notify();
    }

    fn select_target(&mut self, address: String, cx: &mut Context<Self>) {
        self.selected = self
            .catalog
            .available()
            .find(|target| target.address == address)
            .map(|target| target.address.clone());
        self.dropdown_open = false;
        self.status = self
            .selected
            .as_ref()
            .and_then(|selected| self.catalog.find(selected))
            .map(|target| format!("Selected {}", target.name))
            .unwrap_or_else(|| "Selected target expired".into());
        cx.notify();
    }

    fn refresh_targets(&mut self, _: &ClickEvent, _: &mut Window, cx: &mut Context<Self>) {
        self.start_scan(cx);
    }

    fn start_scan(&mut self, cx: &mut Context<Self>) {
        if self.scanning {
            return;
        }
        self.scanning = true;
        self.status = "Scanning for current advertisements".into();
        cx.notify();
        let scan = cx
            .background_executor()
            .spawn(async { discover_bluetooth_targets() });
        cx.spawn(async move |this, cx| {
            let result = scan.await;
            this.update(cx, |view, cx| {
                view.scanning = false;
                match result {
                    Ok(targets) => {
                        view.scan_generation = view.scan_generation.wrapping_add(1);
                        view.catalog.update(targets, view.scan_generation);
                        let selected_exists = view.selected.as_ref().is_some_and(|selected| {
                            view.catalog
                                .available()
                                .any(|target| &target.address == selected)
                        });
                        if !selected_exists {
                            view.selected = view
                                .catalog
                                .available()
                                .next()
                                .map(|target| target.address.clone());
                        }
                        view.status = format!(
                            "Scan complete · {} supported products available",
                            view.catalog.available().count()
                        );
                    }
                    Err(error) => view.status = error,
                }
                cx.notify();
            })
            .ok();
        })
        .detach();
    }

    fn set_connection(&mut self, connect: bool, cx: &mut Context<Self>) {
        let Some(id) = self.selected.clone() else {
            self.status = "Select an available peripheral first".into();
            cx.notify();
            return;
        };
        self.status = if connect {
            "Connecting".into()
        } else {
            "Disconnecting".into()
        };
        cx.notify();
        let operation = cx.background_executor().spawn(async move {
            let result = set_bluetooth_connection(&id, connect);
            (id, result)
        });
        cx.spawn(async move |this, cx| {
            let (id, result) = operation.await;
            this.update(cx, |view, cx| {
                view.status = match result {
                    Ok(()) => {
                        if let Some(target) = view
                            .catalog
                            .targets_mut()
                            .find(|target| target.address == id)
                        {
                            target.connected = connect;
                        }
                        if connect {
                            "Peripheral connected".into()
                        } else {
                            "Peripheral disconnected".into()
                        }
                    }
                    Err(error) => error,
                };
                cx.notify();
            })
            .ok();
        })
        .detach();
    }

    fn connect(&mut self, _: &ClickEvent, _: &mut Window, cx: &mut Context<Self>) {
        self.set_connection(true, cx);
    }

    fn disconnect(&mut self, _: &ClickEvent, _: &mut Window, cx: &mut Context<Self>) {
        self.set_connection(false, cx);
    }

    fn probe(&mut self, _: &ClickEvent, _: &mut Window, cx: &mut Context<Self>) {
        self.status = match self.selected.as_deref().map(probe_device) {
            Some(Ok(probe)) => format!(
                "Battery {} · FW {} · HW {} · {} services · button notify {} · SMP {}",
                probe
                    .battery_percent
                    .map(|value| format!("{value}%"))
                    .unwrap_or_else(|| "N/A".into()),
                probe.firmware_revision.as_deref().unwrap_or("N/A"),
                probe.hardware_revision.as_deref().unwrap_or("N/A"),
                probe.services.len(),
                probe.button_notifications,
                probe.smp
            ),
            Some(Err(error)) => error,
            None => "Select an available peripheral first".into(),
        };
        cx.notify();
    }

    fn send(&mut self, event: ButtonEvent, cx: &mut Context<Self>) {
        let packet = event.packet();
        self.status = format!("Wire packet prepared: {packet:02x?}");
        cx.notify();
    }

    fn press(&mut self, _: &ClickEvent, _: &mut Window, cx: &mut Context<Self>) {
        self.send(ButtonEvent::Press, cx);
    }

    fn release(&mut self, _: &ClickEvent, _: &mut Window, cx: &mut Context<Self>) {
        self.send(ButtonEvent::Release, cx);
    }

    fn single(&mut self, _: &ClickEvent, _: &mut Window, cx: &mut Context<Self>) {
        self.send(ButtonEvent::Single, cx);
    }

    fn double(&mut self, _: &ClickEvent, _: &mut Window, cx: &mut Context<Self>) {
        self.send(ButtonEvent::Double, cx);
    }

    fn long(&mut self, _: &ClickEvent, _: &mut Window, cx: &mut Context<Self>) {
        self.send(ButtonEvent::Long, cx);
    }

    fn select_firmware(&mut self, _: &ClickEvent, _: &mut Window, cx: &mut Context<Self>) {
        self.status = match select_firmware_path() {
            Ok(Some(path)) => match FirmwareImage::validate(&path) {
                Ok(image) => {
                    let status = format!("Validated firmware {}", image.version);
                    self.image = Some(image);
                    status
                }
                Err(error) => error,
            },
            Ok(None) => "Firmware selection cancelled".into(),
            Err(error) => error,
        };
        cx.notify();
    }

    fn start_flash(&mut self, _: &ClickEvent, _: &mut Window, cx: &mut Context<Self>) {
        let product = self.selected.as_ref().and_then(|selected| {
            self.catalog
                .find(selected)
                .and_then(|target| target.product)
        });
        self.status = if product != Some(Product::OmiDevKit) {
            "Host flashing is only implemented for Omi DevKit".into()
        } else if let Some(image) = &self.image {
            let serial = env::var("OMI_EMULATOR_SERIAL").unwrap_or_default();
            match FlashSession::start_devkit(image, &serial) {
                Ok(session) => {
                    self.flash = Some(session);
                    "Flash started · select CHECK PROGRESS to refresh".into()
                }
                Err(error) => error,
            }
        } else {
            "Select and validate a firmware image first".into()
        };
        cx.notify();
    }

    fn poll_flash(&mut self, _: &ClickEvent, _: &mut Window, cx: &mut Context<Self>) {
        self.status = match self.flash.as_mut().map(FlashSession::poll) {
            Some(Ok(Some(true))) => {
                self.flash = None;
                "Flash completed successfully".into()
            }
            Some(Ok(Some(false))) => {
                self.flash = None;
                "Flash failed; adafruit-nrfutil returned an error".into()
            }
            Some(Ok(None)) => "Flash in progress".into(),
            Some(Err(error)) => error,
            None => "No flash is running".into(),
        };
        cx.notify();
    }

    fn cancel_flash(&mut self, _: &ClickEvent, _: &mut Window, cx: &mut Context<Self>) {
        self.status = match self.flash.as_mut() {
            Some(session) => match session.cancel() {
                Ok(()) => {
                    self.flash = None;
                    "Flash cancelled".into()
                }
                Err(error) => error,
            },
            None => "No flash is running".into(),
        };
        cx.notify();
    }
}

impl Render for EmulatorView {
    fn render(&mut self, _window: &mut Window, cx: &mut Context<Self>) -> impl IntoElement {
        let selected = self
            .selected
            .as_ref()
            .and_then(|selected| self.catalog.find(selected));
        let product = selected.and_then(|target| target.product);
        let capabilities = product.map(Product::capabilities).unwrap_or_default();
        let product_name = product.map(Product::name).unwrap_or("Unknown product");
        let capability_summary = capabilities.summary();
        let target = selected
            .map(target_label)
            .unwrap_or_else(|| "No Bluetooth targets discovered".into());
        let status = self.status.clone();
        let dropdown_open = self.dropdown_open;
        let button_ready = capabilities.button;
        let firmware = self
            .image
            .as_ref()
            .map(|image| format!("{}  ·  {} bytes", image.version, image.bytes))
            .unwrap_or_else(|| "Set OMI_EMULATOR_FIRMWARE to select an image".into());
        let target_options = div()
            .flex()
            .flex_col()
            .max_h(px(220.))
            .border_1()
            .border_color(rgb(0x3f3f46))
            .rounded_md()
            .children(self.catalog.available().enumerate().map(|(index, target)| {
                let address = target.address.clone();
                div()
                    .id(("target", index))
                    .px_3()
                    .py_1()
                    .text_sm()
                    .bg(rgb(0x18181b))
                    .hover(|style| style.bg(rgb(0x27272a)))
                    .cursor_pointer()
                    .on_click(
                        cx.listener(move |this, _, _, cx| this.select_target(address.clone(), cx)),
                    )
                    .child(target_label(target))
            }));
        let profile_reference =
            div()
                .flex()
                .flex_col()
                .gap_0p5()
                .children(Product::ALL.into_iter().map(|profile| {
                    div().text_xs().text_color(rgb(0xa1a1aa)).child(format!(
                        "{} · {}",
                        profile.name(),
                        profile.capabilities().summary()
                    ))
                }));
        view! {r#"
            div w-full h-full bg-zinc-950 text-white flex flex-col p-8 gap-6
                div flex flex-row justify-between items-end border-b border-zinc-800 pb-5
                    div flex flex-col gap-1
                        div text-xs text-zinc-500 font-medium
                            "BASED HARDWARE / FIRMWARE LAB"
                        div text-4xl font-bold
                            "PRODUCT TEST BENCH"
                    div text-xs text-zinc-500
                        "RUST CORE · CREPUSCULARITY / GPUI"

                div flex flex-row gap-2
                    button flex-1 bg-zinc-900 border border-zinc-700 text-white font-medium px-3 py-2 rounded-md @click=toggle_targets
                        "{target}  ▾"
                    button bg-zinc-800 text-white font-medium px-3 py-2 rounded-md @click=refresh_targets
                        "SCAN"
                    button bg-zinc-100 text-zinc-950 font-medium px-3 py-2 rounded-md @click=connect
                        "CONNECT"
                    button bg-zinc-800 text-white font-medium px-3 py-2 rounded-md @click=disconnect
                        "DISCONNECT"
                    button bg-zinc-800 text-white font-medium px-3 py-2 rounded-md @click=probe
                        "PROBE"

                if {dropdown_open}
                    {target_options}

                div bg-zinc-900 border border-zinc-800 rounded-md p-3 flex flex-col gap-1
                    div text-xs text-zinc-500
                        "DETECTED PRODUCT · {product_name}"
                    div text-sm text-zinc-200
                        "{capability_summary}"

                div bg-zinc-900 border border-zinc-800 rounded-md p-3 flex flex-col gap-3
                    div text-xs text-zinc-500
                        "BUTTON SIGNAL GENERATOR"
                    if {button_ready}
                        div flex flex-row gap-2
                            button bg-zinc-100 text-zinc-950 font-medium px-3 py-2 rounded-md @click=press
                                "PRESS · 04"
                            button bg-zinc-800 text-white font-medium px-3 py-2 rounded-md @click=release
                                "RELEASE · 05"
                            button bg-zinc-800 text-white font-medium px-3 py-2 rounded-md @click=single
                                "SINGLE · 01"
                            button bg-zinc-800 text-white font-medium px-3 py-2 rounded-md @click=double
                                "DOUBLE · 02"
                            button bg-zinc-800 text-white font-medium px-3 py-2 rounded-md @click=long
                                "LONG · 03"
                    else
                        div text-zinc-500
                            "No repository-backed button contract for this product"

                div flex flex-row gap-4
                    div flex-1 bg-zinc-900 border border-zinc-800 rounded-md p-3 flex flex-col gap-2
                        div text-xs text-zinc-500
                            "FIRMWARE IMAGE"
                        div text-sm
                            "{firmware}"
                        div flex flex-row gap-2
                            button bg-zinc-800 text-white font-medium px-3 py-2 rounded-md @click=select_firmware
                                "SELECT IMAGE"
                            button bg-zinc-100 text-zinc-950 font-medium px-3 py-2 rounded-md @click=start_flash
                                "FLASH DEVKIT"
                            button bg-zinc-800 text-white font-medium px-3 py-2 rounded-md @click=poll_flash
                                "CHECK PROGRESS"
                            button bg-zinc-800 text-white font-medium px-3 py-2 rounded-md @click=cancel_flash
                                "CANCEL"
                        div text-xs text-zinc-500
                            "DevKit flash uses adafruit-nrfutil and OMI_EMULATOR_SERIAL. Other products report unsupported."
                    div flex-1 bg-zinc-900 border border-zinc-800 rounded-md p-3 flex flex-col gap-2
                        div text-xs text-zinc-500
                            "DEVICE CONTRACTS"
                        div text-sm
                            "Audio · Battery · Device info · Settings · Storage"
                        div text-xs text-zinc-500
                            "Only READY capabilities map to contracts present in this repository."
                        {profile_reference}

                div mt-auto border-t border-zinc-800 pt-4 text-sm text-zinc-400
                    "{status}"
        "#}
    }
}

fn selected_path(success: bool, stdout: Vec<u8>) -> Result<Option<String>, String> {
    if !success {
        return Ok(None);
    }
    let path = String::from_utf8(stdout)
        .map_err(|error| error.to_string())?
        .trim()
        .trim_matches('"')
        .to_owned();
    Ok((!path.is_empty()).then_some(path))
}

#[cfg(target_os = "macos")]
fn select_firmware_path() -> Result<Option<String>, String> {
    std::process::Command::new("osascript")
        .args([
            "-e",
            "POSIX path of (choose file with prompt \"Select an Omi firmware ZIP\")",
        ])
        .output()
        .map_err(|error| error.to_string())
        .and_then(|output| selected_path(output.status.success(), output.stdout))
}

#[cfg(target_os = "linux")]
fn select_firmware_path() -> Result<Option<String>, String> {
    std::process::Command::new("zenity")
        .args([
            "--file-selection",
            "--title=Select an Omi firmware ZIP",
            "--file-filter=Firmware ZIP | *.zip",
        ])
        .output()
        .map_err(|error| format!("could not open zenity: {error}"))
        .and_then(|output| selected_path(output.status.success(), output.stdout))
}

#[cfg(target_os = "windows")]
fn select_firmware_path() -> Result<Option<String>, String> {
    std::process::Command::new("powershell")
        .args([
            "-NoProfile",
            "-Command",
            "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.OpenFileDialog; $d.Filter='Firmware ZIP (*.zip)|*.zip'; if($d.ShowDialog() -eq 'OK'){$d.FileName}",
        ])
        .output()
        .map_err(|error| format!("could not open Windows file picker: {error}"))
        .and_then(|output| selected_path(output.status.success(), output.stdout))
}

fn target_label(target: &BluetoothTarget) -> String {
    let product = target.product.map(Product::name).unwrap_or("Unknown");
    let rssi = target
        .rssi
        .map(|rssi| format!("{rssi} dBm"))
        .unwrap_or_else(|| "RSSI unavailable".into());
    let state = if target.connected {
        "CONNECTED"
    } else if target.available {
        "AVAILABLE"
    } else {
        "UNAVAILABLE"
    };
    format!(
        "{}  ·  {}  ·  {}  ·  {}  ·  {}",
        target.name, product, rssi, state, target.address
    )
}

fn main() {
    Application::new().run(|cx: &mut App| {
        let options = gpui_window_options(
            "com.basedhardware.omi-product-emulator",
            "Omi Product Test Bench",
            Some(gpui::WindowBounds::Windowed(bounds(
                point(px(120.), px(100.)),
                size(px(1100.), px(760.)),
            ))),
            Some(size(px(900.), px(640.))),
        );
        cx.open_window(options, |_window, cx| cx.new(EmulatorView::new))
            .unwrap();
    });
}

#[cfg(test)]
mod tests {
    use super::selected_path;

    #[test]
    fn normalizes_native_file_picker_output() {
        assert_eq!(
            selected_path(true, b"\"C:\\firmware\\omi.zip\"\r\n".to_vec()).unwrap(),
            Some("C:\\firmware\\omi.zip".into())
        );
        assert_eq!(selected_path(true, b"\n".to_vec()).unwrap(), None);
        assert_eq!(selected_path(false, b"ignored.zip".to_vec()).unwrap(), None);
    }
}
