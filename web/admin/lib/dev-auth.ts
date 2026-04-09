export const DEV_BYPASS_ENABLED =
  process.env.NODE_ENV !== "production" &&
  (process.env.NEXT_PUBLIC_DEV_BYPASS_AUTH === "1" || process.env.DEV_BYPASS_AUTH === "1");

export const DEV_BYPASS_UID = "dev-admin";
export const DEV_BYPASS_TOKEN = "dev-bypass-token";
