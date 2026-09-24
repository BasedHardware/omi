export const logger = {
  error: (msg: string, meta?: Record<string, any>) => {
    // Replace with your preferred logging framework
    console.error(msg, meta);
  },
  info: (msg: string, meta?: Record<string, any>) => {
    console.info(msg, meta);
  },
};
