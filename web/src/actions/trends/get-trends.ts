'use server';
import envConfig from '@/src/constants/envConfig';

export default async function getTrends() {
  try {
    const response = await fetch(`${envConfig.API_URL}/v1/trends`, {
      cache: 'no-cache',
    });

    if (!response.ok) {
      return response;
    }

    const data = await response.json();

    return data;
  } catch (error) {
    return undefined;
  }
}
