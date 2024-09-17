'use server';
import envConfig from '@/src/constants/envConfig';

export default async function getTrends() {
  console.log('URL FROM ACTIONS:', `${envConfig.API_URL}/v1/trends`);
  try {
      const response = await fetch(`${JSON.stringify(envConfig.API_URL)}/v1/trends`, {
        cache: 'no-cache',
      });

      if(!response.ok){
        return undefined;
      }

      const data = await response.json();
      return data;
  } catch (error) {
    return undefined;
  }
}
