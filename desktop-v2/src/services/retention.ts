import { invoke } from "@tauri-apps/api/core";

export async function getRetentionDays(): Promise<number> {
  return invoke<number>("plugin:screen-capture|get_retention_days");
}

export async function setRetentionDays(days: number): Promise<void> {
  await invoke<void>("plugin:screen-capture|set_retention_days", { days });
}
