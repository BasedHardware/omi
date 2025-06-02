'use server';
import envConfig from '@/src/constants/envConfig';

export interface GenerateDescriptionRequest {
  name: string;
  description: string;
}

export interface GenerateDescriptionResponse {
  description: string;
}

export default async function generateDescription(
  data: GenerateDescriptionRequest,
  token: string
): Promise<GenerateDescriptionResponse | null> {
  const apiUrl = envConfig.API_URL || 'http://localhost:8000';
  
  try {
    const response = await fetch(`${apiUrl}/v1/app/generate-description`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(data),
    });
    
    if (!response.ok) {
      console.error('Failed to generate description:', response.status, response.statusText);
      return null;
    }
    
    return await response.json();
  } catch (error) {
    console.error('Error generating description:', error);
    return null;
  }
} 