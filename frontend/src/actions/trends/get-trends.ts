'use server';
import envConfig from '@/src/constants/envConfig';

export default async function getTrends() {
  try {
      const response = await fetch(`${JSON.stringify(envConfig.API_URL)}/v1/trends`, {
        next: { revalidate: 60 },
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
