'use server';

const BASE_URL = process.env.API_URL;

export default async function getMemory(id: string) {
  const response = await fetch(`${BASE_URL}/v1/memories/${id}`);
  if (!response.ok) {
    throw new Error('Failed to fetch memory');
  }
  return response.json();
}