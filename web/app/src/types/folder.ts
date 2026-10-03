import { t } from '@/lib/i18n';
// Folder Types

export interface Folder {
  id: string;
  name: string;
  description?: string;
  emoji?: string; // Frontend display (mapped from icon)
  icon?: string; // Backend field
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
  {
    id: 'slate',
    value: '#64748B',
    get label() {
      return t('Slate');
    },
  },
  {
    id: 'blue',
    value: '#3B82F6',
    get label() {
      return t('Blue');
    },
  },
  {
    id: 'green',
    value: '#10B981',
    get label() {
      return t('Green');
    },
  },
  {
    id: 'yellow',
    value: '#F59E0B',
    get label() {
      return t('Yellow');
    },
  },
  {
    id: 'red',
    value: '#EF4444',
    get label() {
      return t('Red');
    },
  },
  {
    id: 'pink',
    value: '#EC4899',
    get label() {
      return t('Pink');
    },
  },
  {
    id: 'orange',
    value: '#F97316',
    get label() {
      return t('Orange');
    },
  },
  {
    id: 'teal',
    value: '#14B8A6',
    get label() {
      return t('Teal');
    },
  },
] as const;

// Predefined folder emojis (matching mobile app)
export const FOLDER_EMOJIS = [
  '📁',
  '💼',
  '❤️',
  '👥',
  '🏠',
  '💡',
  '🎯',
  '📚',
  '🔧',
  '🎨',
  '🎮',
  '🏃',
  '✈️',
  '🍔',
  '🎵',
  '📷',
] as const;

export type FolderColor = (typeof FOLDER_COLORS)[number]['id'];
export type FolderEmoji = (typeof FOLDER_EMOJIS)[number];
