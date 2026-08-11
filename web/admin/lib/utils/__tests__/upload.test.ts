import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { uploadImage, isValidImage, isValidFileSize } from '../upload';
import { ref, uploadBytes, getDownloadURL } from 'firebase/storage';
import { getFirebaseStorage } from '@/lib/firebase/client';

// Mock dependencies
vi.mock('firebase/storage', () => ({
  ref: vi.fn(),
  uploadBytes: vi.fn(),
  getDownloadURL: vi.fn(),
}));

vi.mock('@/lib/firebase/client', () => ({
  getFirebaseStorage: vi.fn(),
}));

describe('upload utils', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('uploadImage', () => {
    beforeEach(() => {
      // Mock Date.now() for predictable timestamps
      vi.useFakeTimers();
      vi.setSystemTime(new Date(1600000000000));
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should upload a file and return the download URL', async () => {
      // Arrange
      const mockFile = new File(['test content'], 'test-image.jpg', { type: 'image/jpeg' });
      const mockStorage = {};
      const mockStorageRef = {};
      const mockSnapshot = { ref: {} };
      const mockDownloadUrl = 'https://example.com/test-image.jpg';

      vi.mocked(getFirebaseStorage).mockReturnValue(mockStorage as any);
      vi.mocked(ref).mockReturnValue(mockStorageRef as any);
      vi.mocked(uploadBytes).mockResolvedValue(mockSnapshot as any);
      vi.mocked(getDownloadURL).mockResolvedValue(mockDownloadUrl);

      // Act
      const result = await uploadImage(mockFile);

      // Assert
      expect(getFirebaseStorage).toHaveBeenCalled();
      expect(ref).toHaveBeenCalledWith(mockStorage, 'announcements/1600000000000_test-image.jpg');
      expect(uploadBytes).toHaveBeenCalledWith(mockStorageRef, mockFile);
      expect(getDownloadURL).toHaveBeenCalledWith(mockSnapshot.ref);
      expect(result).toBe(mockDownloadUrl);
    });

    it('should handle custom folders and sanitize file names', async () => {
      // Arrange
      const mockFile = new File(['test content'], 'my image!@#.png', { type: 'image/png' });
      const mockStorage = {};
      const mockStorageRef = {};
      const mockSnapshot = { ref: {} };
      const mockDownloadUrl = 'https://example.com/my-image.png';

      vi.mocked(getFirebaseStorage).mockReturnValue(mockStorage as any);
      vi.mocked(ref).mockReturnValue(mockStorageRef as any);
      vi.mocked(uploadBytes).mockResolvedValue(mockSnapshot as any);
      vi.mocked(getDownloadURL).mockResolvedValue(mockDownloadUrl);

      // Act
      const result = await uploadImage(mockFile, 'custom-folder');

      // Assert
      // "my image!@#.png" -> "my_image___.png"
      expect(ref).toHaveBeenCalledWith(mockStorage, 'custom-folder/1600000000000_my_image___.png');
      expect(uploadBytes).toHaveBeenCalledWith(mockStorageRef, mockFile);
      expect(getDownloadURL).toHaveBeenCalledWith(mockSnapshot.ref);
      expect(result).toBe(mockDownloadUrl);
    });
  });

  describe('isValidImage', () => {
    it('should return true for valid image types', () => {
      expect(isValidImage(new File([], 'test.jpg', { type: 'image/jpeg' }))).toBe(true);
      expect(isValidImage(new File([], 'test.png', { type: 'image/png' }))).toBe(true);
      expect(isValidImage(new File([], 'test.gif', { type: 'image/gif' }))).toBe(true);
      expect(isValidImage(new File([], 'test.webp', { type: 'image/webp' }))).toBe(true);
    });

    it('should return false for invalid image types', () => {
      expect(isValidImage(new File([], 'test.pdf', { type: 'application/pdf' }))).toBe(false);
      expect(isValidImage(new File([], 'test.txt', { type: 'text/plain' }))).toBe(false);
      expect(isValidImage(new File([], 'test.mp4', { type: 'video/mp4' }))).toBe(false);
      expect(isValidImage(new File([], 'test', { type: '' }))).toBe(false);
    });
  });

  describe('isValidFileSize', () => {
    it('should return true for file size under the limit', () => {
      // 1 MB
      const file = new File([new ArrayBuffer(1024 * 1024)], 'test.jpg');
      expect(isValidFileSize(file)).toBe(true);
    });

    it('should return true for file size exactly at the default limit', () => {
      // 5 MB
      const file = new File([new ArrayBuffer(5 * 1024 * 1024)], 'test.jpg');
      expect(isValidFileSize(file)).toBe(true);
    });

    it('should return false for file size exceeding the default limit', () => {
      // 5.1 MB
      const file = new File([new ArrayBuffer(5.1 * 1024 * 1024)], 'test.jpg');
      expect(isValidFileSize(file)).toBe(false);
    });

    it('should respect custom maxSizeMB limit', () => {
      // 2 MB file with 1 MB limit should fail
      const file1 = new File([new ArrayBuffer(2 * 1024 * 1024)], 'test.jpg');
      expect(isValidFileSize(file1, 1)).toBe(false);

      // 2 MB file with 3 MB limit should pass
      const file2 = new File([new ArrayBuffer(2 * 1024 * 1024)], 'test.jpg');
      expect(isValidFileSize(file2, 3)).toBe(true);

      // Exactly at custom limit
      const file3 = new File([new ArrayBuffer(2 * 1024 * 1024)], 'test.jpg');
      expect(isValidFileSize(file3, 2)).toBe(true);
    });
  });
});
