'use server';

import envConfig from '@/src/constants/envConfig';
import { ResponseTrends } from '@/src/types/trends/trends.types';

export default async function getTrends(): Promise<ResponseTrends> {
  const response = await fetch(`${envConfig.API_URL}/v1/trends`, { next: { revalidate: 60 } });
  const data = await response.json();
  return data;
}
