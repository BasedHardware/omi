use chrono::{DateTime, Local};
use dioxus::prelude::*;

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

impl From<omi_db::notification_log::NotificationRecord> for NotificationEntry {
    fn from(r: omi_db::notification_log::NotificationRecord) -> Self {
        Self {
            title: r.title,
            body: r.body,
            timestamp: r.created_at,
            priority: r.priority,
        }
    }
}

pub fn record_and_push(
    db: &Option<crate::app::Db>,
    mut history: Signal<Vec<NotificationEntry>>,
    title: &str,
    body: &str,
    priority: u8,
) {
    if let Some(crate::app::Db(ref d)) = db {
        let _ = d.insert_notification(title, body, priority);
    }
    let entry = NotificationEntry::new(title, body, priority);
    let mut list = history.read().clone();
    list.push(entry);
    if list.len() > 100 {
        list.drain(0..list.len() - 100);
    }
    history.set(list);
}

pub fn load_from_db(
    db: &Option<crate::app::Db>,
    mut history: Signal<Vec<NotificationEntry>>,
) {
    if let Some(crate::app::Db(ref d)) = db {
        if let Ok(records) = d.list_notifications(50) {
            let entries: Vec<NotificationEntry> = records
                .into_iter()
                .rev()
                .map(NotificationEntry::from)
                .collect();
            history.set(entries);
        }
    }
}
