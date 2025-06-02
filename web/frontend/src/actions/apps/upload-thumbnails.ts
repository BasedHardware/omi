'use server';
import uploadThumbnail from './upload-thumbnail';

export default async function uploadThumbnails(
  thumbnailUrls: string[],
  token: string
): Promise<string[]> {
  const thumbnailIds: string[] = [];
  
  if (thumbnailUrls.length === 0) {
    return thumbnailIds;
  }
  
  console.log('📸 [uploadThumbnails] Uploading thumbnails...');
  
  for (const thumbnailUrl of thumbnailUrls) {
    try {
      const response = await fetch(thumbnailUrl);
      const blob = await response.blob();
      const thumbnailFormData = new FormData();
      thumbnailFormData.append('file', blob, 'thumbnail.jpg');
      
      const thumbnailResult = await uploadThumbnail(thumbnailFormData, token);
      
      if (thumbnailResult) {
        thumbnailIds.push(thumbnailResult.thumbnail_id);
        console.log('📸 [uploadThumbnails] Thumbnail uploaded successfully:', thumbnailResult.thumbnail_id);
      } else {
        console.warn('⚠️ [uploadThumbnails] Failed to upload thumbnail');
      }
    } catch (thumbnailError) {
      console.warn('⚠️ [uploadThumbnails] Error uploading thumbnail, continuing:', thumbnailError);
    }
  }
  
  console.log('📸 [uploadThumbnails] Thumbnail IDs collected:', thumbnailIds);
  return thumbnailIds;
} 