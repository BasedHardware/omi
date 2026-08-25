// Folder Types

export interface Folder {
  id: string;
  name: string;
  description?: string;
  emoji?: string; // Frontend display (mapped from icon)
  icon?: string;  // Backend field
  color?: string;
  conversation_count?: number;
  created_at: string;
  updated_at?: string;
  order?: number;
  is_system?: boolean;
}

export interface CreateFolderRequest {
  name: string;
  description?: string;
  emoji?: string;
  icon?: string;
  color?: string;
}

export interface UpdateFolderRequest {
  name?: string;
  description?: string;
  emoji?: string;
  icon?: string;
  color?: string;
}

export interface MoveConversationToFolderRequest {
  folder_id: string | null; // null to remove from folder
}

export interface BulkMoveConversationsRequest {
  conversation_ids: string[];
}

export interface ReorderFoldersRequest {
  folder_ids: string[]; // ordered list of folder IDs
}

// Predefined folder colors
export const FOLDER_COLORS = [
  { id: 'purple', value: '#8B5CF6', label: 'Purple' },
  { id: 'blue', value: '#3B82F6', label: 'Blue' },
  { id: 'green', value: '#10B981', label: 'Green' },
  { id: 'yellow', value: '#F59E0B', label: 'Yellow' },
  { id: 'red', value: '#EF4444', label: 'Red' },
  { id: 'pink', value: '#EC4899', label: 'Pink' },
  { id: 'orange', value: '#F97316', label: 'Orange' },
  { id: 'teal', value: '#14B8A6', label: 'Teal' },
] as const;

// Predefined folder emojis (matching mobile app)
export const FOLDER_EMOJIS = [
  '📁', '💼', '❤️', '👥', '🏠', '💡', '🎯', '📚',
  '🔧', '🎨', '🎮', '🏃', '✈️', '🍔', '🎵', '📷',
] as const;

export type FolderColor = typeof FOLDER_COLORS[number]['id'];
export type FolderEmoji = typeof FOLDER_EMOJIS[number];
