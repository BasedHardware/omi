const envConfig = {
  API_URL:
    process.env.NEXT_PUBLIC_NODE_ENV === 'development'
      ? process.env.API_URL_DEV
      : process.env.API_URL_PROD,
  API_URL_DEV: process.env.API_URL_DEV,
  API_URL_PROD: process.env.API_URL_PROD,
  NODE_ENV: process.env.NEXT_PUBLIC_NODE_ENV,
  IS_DEVELOPMENT: process.env.NEXT_PUBLIC_NODE_ENV === 'development',
  odeploymentUrl:
    process.env.NEXT_PUBLIC_NODE_ENV === 'development'
      ? process.env.API_URL_DEV
      : process.env.API_URL_PROD,
};

export default envConfig;
