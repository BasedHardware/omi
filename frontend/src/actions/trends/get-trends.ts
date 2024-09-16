'use server';

import envConfig from '@/src/constants/envConfig';
import { ResponseTrends } from '@/src/types/trends/trends.types';

export default async function getTrends(): Promise<ResponseTrends> {
  console.log('URL:', `${envConfig.API_URL}/v1/trends`);
  try {
      const response = await fetch(`${envConfig.API_URL}/v1/trends`, {
        next: { revalidate: 60 },
      });

      if(!response.ok){
        throw new Error('Failed to fetch trends');
      }

      const data = await response.json();
      return data;
  } catch (error) {
    throw new Error(error);
  }
}
