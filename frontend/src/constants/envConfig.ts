const envConfig = {
  API_URL: process.env.API_URL,
  NODE_ENV: process.env.NEXT_PUBLIC_NODE_ENV,
  IS_DEVELOPMENT: process.env.NEXT_PUBLIC_NODE_ENV === 'development',
  deploymentUrl:
    process.env.NEXT_PUBLIC_NODE_ENV === 'development'
      ? process.env.API_URL
      : 'https://omi.me/',
};

export default envConfig;
