'use server';
import envConfig from '@/src/constants/envConfig';

export interface UploadThumbnailResponse {
  thumbnail_id: string;
}

export default async function uploadThumbnail(
  formData: FormData,
  token: string
): Promise<UploadThumbnailResponse | null> {
  const apiUrl = envConfig.API_URL || 'http://localhost:8000';
  
  try {
    const response = await fetch(`${apiUrl}/v1/app/thumbnails`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`
      },
      body: formData,
    });
    
    if (!response.ok) {
      console.error('Failed to upload thumbnail:', response.status, response.statusText);
      return null;
    }
    
    return await response.json();
  } catch (error) {
    console.error('Error uploading thumbnail:', error);
    return null;
  }
} 