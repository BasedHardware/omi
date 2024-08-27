'use server';

const BASE_URL = process.env.API_URL;

// example: 32190a0f-8229-4189-93a9-ba8156c952cb

export default async function getMemory(id: string) {
  try {
    const response = await fetch(`${BASE_URL}/v1/memories/${id}`, {
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer 123${process.env.TEST_ID}`,
      },
    });
    if (!response.ok) {
      throw new Error('Failed to fetch memory');
    }
    return await response.json();
  } catch (err) {
    throw new Error(err.message);
  }
}
