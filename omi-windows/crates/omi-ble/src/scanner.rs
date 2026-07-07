use std::time::Duration;

use anyhow::{Context, Result};
use btleplug::api::{Central, Manager as _, Peripheral as _, ScanFilter};
use btleplug::platform::{Adapter, Manager, Peripheral};
use tokio::sync::mpsc;
use tracing::{info, warn};
use uuid::Uuid;

use crate::protocol::{DeviceType, OMI_SERVICE_UUID};

#[derive(Debug, Clone)]
pub struct DiscoveredDevice {
    pub name: String,
    pub id: String,
    pub rssi: i16,
    pub device_type: DeviceType,
    pub peripheral: Peripheral,
}

pub async fn get_adapter() -> Result<Adapter> {
    let manager = Manager::new().await.context("Failed to create BLE manager")?;
    let adapters = manager.adapters().await.context("Failed to list BLE adapters")?;
    adapters
        .into_iter()
        .next()
        .context("No Bluetooth adapter found")
}

pub async fn scan_for_devices(
    duration: Duration,
    tx: mpsc::Sender<DiscoveredDevice>,
) -> Result<()> {
    let adapter = get_adapter().await?;

    let omi_uuid = Uuid::parse_str(OMI_SERVICE_UUID).unwrap();
    let filter = ScanFilter {
        services: vec![omi_uuid],
    };

    info!("[BLE] Starting scan ({}s)...", duration.as_secs());
    adapter
        .start_scan(filter)
        .await
        .context("Failed to start BLE scan")?;

    tokio::time::sleep(duration).await;

    let peripherals = adapter.peripherals().await.unwrap_or_default();
    info!("[BLE] Scan complete, found {} peripherals", peripherals.len());

    for p in peripherals {
        let props = match p.properties().await {
            Ok(Some(props)) => props,
            _ => continue,
        };

        let name = props.local_name.unwrap_or_default();
        if name.is_empty() {
            continue;
        }

        let rssi = props.rssi.unwrap_or(0);
        let device_type = DeviceType::from_name(&name);
        let id = p.id().to_string();

        let device = DiscoveredDevice {
            name,
            id,
            rssi,
            device_type,
            peripheral: p,
        };

        if tx.send(device).await.is_err() {
            break;
        }
    }

    adapter.stop_scan().await.ok();
    Ok(())
}

pub async fn scan_all_ble(
    duration: Duration,
    tx: mpsc::Sender<DiscoveredDevice>,
) -> Result<()> {
    let adapter = get_adapter().await?;

    info!("[BLE] Starting unfiltered scan ({}s)...", duration.as_secs());
    adapter
        .start_scan(ScanFilter::default())
        .await
        .context("Failed to start BLE scan")?;

    tokio::time::sleep(duration).await;

    let peripherals = adapter.peripherals().await.unwrap_or_default();
    let omi_uuid = Uuid::parse_str(OMI_SERVICE_UUID).unwrap();

    for p in peripherals {
        let props = match p.properties().await {
            Ok(Some(props)) => props,
            _ => continue,
        };

        let name = props.local_name.clone().unwrap_or_default();
        let has_omi_service = props.services.contains(&omi_uuid);
        let device_type = DeviceType::from_name(&name);

        let is_known = has_omi_service || device_type != DeviceType::Unknown;
        if !is_known {
            continue;
        }

        let rssi = props.rssi.unwrap_or(0);
        let id = p.id().to_string();

        let device = DiscoveredDevice {
            name: if name.is_empty() { id.clone() } else { name },
            id,
            rssi,
            device_type,
            peripheral: p,
        };

        if tx.send(device).await.is_err() {
            break;
        }
    }

    adapter.stop_scan().await.ok();
    Ok(())
}

pub async fn find_device_by_id(device_id: &str) -> Result<Option<Peripheral>> {
    let adapter = get_adapter().await?;

    adapter
        .start_scan(ScanFilter::default())
        .await
        .context("Failed to start scan")?;

    tokio::time::sleep(Duration::from_secs(5)).await;

    let peripherals = adapter.peripherals().await.unwrap_or_default();
    for p in peripherals {
        if p.id().to_string() == device_id {
            adapter.stop_scan().await.ok();
            return Ok(Some(p));
        }
    }

    adapter.stop_scan().await.ok();
    warn!("[BLE] Device {device_id} not found");
    Ok(None)
}
