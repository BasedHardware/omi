use chrono::{DateTime, Local};

#[derive(Clone, Debug)]
pub struct NotificationEntry {
    pub title: String,
    pub body: String,
    pub timestamp: DateTime<Local>,
    pub priority: u8,
}

impl NotificationEntry {
    pub fn new(title: &str, body: &str, priority: u8) -> Self {
        Self {
            title: title.to_string(),
            body: body.to_string(),
            timestamp: Local::now(),
            priority,
        }
    }

    pub fn time_str(&self) -> String {
        self.timestamp.format("%H:%M").to_string()
    }
}
