use std::env;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::PathBuf;

use anyhow::{Context, Result};
use directories::ProjectDirs;

const DEFAULT_HOST: IpAddr = IpAddr::V4(Ipv4Addr::LOCALHOST);
const DEFAULT_PORT: u16 = 8765;

#[derive(Clone, Debug)]
pub struct Config {
    pub bind_addr: SocketAddr,
    pub data_dir: PathBuf,
}

impl Config {
    pub fn from_env() -> Result<Self> {
        let host = env::var("OMI_LOCAL_BACKEND_HOST")
            .ok()
            .map(|value| value.parse::<IpAddr>())
            .transpose()
            .context("OMI_LOCAL_BACKEND_HOST must be an IP address")?
            .unwrap_or(DEFAULT_HOST);

        let port = env::var("OMI_LOCAL_BACKEND_PORT")
            .ok()
            .map(|value| value.parse::<u16>())
            .transpose()
            .context("OMI_LOCAL_BACKEND_PORT must be a valid TCP port")?
            .unwrap_or(DEFAULT_PORT);

        let data_dir = match env::var("OMI_LOCAL_BACKEND_DATA_DIR") {
            Ok(value) => PathBuf::from(value),
            Err(_) => default_data_dir()?,
        };

        Ok(Self {
            bind_addr: SocketAddr::new(host, port),
            data_dir,
        })
    }
}

fn default_data_dir() -> Result<PathBuf> {
    let project_dirs = ProjectDirs::from("com", "omi", "Omi Local Backend")
        .context("could not resolve a local data directory for this platform")?;
    Ok(project_dirs.data_local_dir().to_path_buf())
}
