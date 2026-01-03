'use client';

import { useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { Plus, Star, Pencil, Trash2, Inbox, Briefcase, Heart, Users } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Folder } from '@/types/folder';

// Special folder IDs for built-in tabs
export const FOLDER_ALL = 'all';
export const FOLDER_STARRED = 'starred';

interface FolderTabsProps {
  folders: Folder[];
  selectedFolderId: string;
  onSelectFolder: (folderId: string) => void;
  onCreateFolder: () => void;
  onEditFolder?: (folder: Folder) => void;
  onDeleteFolder?: (folder: Folder) => void;
  loading?: boolean;
}

export function FolderTabs({
  folders,
  selectedFolderId,
  onSelectFolder,
  onCreateFolder,
  onEditFolder,
  onDeleteFolder,
  loading = false,
}: FolderTabsProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [contextMenu, setContextMenu] = useState<{ folder: Folder; x: number; y: number } | null>(null);

  const handleContextMenu = (e: React.MouseEvent, folder: Folder) => {
    e.preventDefault();
    setContextMenu({ folder, x: e.clientX, y: e.clientY });
  };

  const closeContextMenu = () => setContextMenu(null);

  return (
    <div className="relative">
      {/* Tabs container - wraps instead of scrolling */}
      <div
        ref={scrollRef}
        className="flex items-center gap-2 flex-wrap"
      >
        {/* All tab - always first */}
        <TabButton
          label="All"
          icon={<Inbox className="w-3.5 h-3.5" />}
          isSelected={selectedFolderId === FOLDER_ALL}
          onClick={() => onSelectFolder(FOLDER_ALL)}
        />

        {/* Starred tab - always second */}
        <TabButton
          label="Starred"
          icon={<Star className="w-3.5 h-3.5" />}
          isSelected={selectedFolderId === FOLDER_STARRED}
          onClick={() => onSelectFolder(FOLDER_STARRED)}
        />

        {/* User folders */}
        {folders.map((folder) => (
          <TabButton
            key={folder.id}
            label={folder.name}
            emoji={folder.emoji}
            color={folder.color}
            isSelected={selectedFolderId === folder.id}
            onClick={() => onSelectFolder(folder.id)}
            onContextMenu={(e) => handleContextMenu(e, folder)}
          />
        ))}

        {/* Add folder button */}
        <button
          onClick={onCreateFolder}
          disabled={loading}
          className={cn(
            'flex-shrink-0 flex items-center justify-center',
            'w-8 h-8 rounded-full',
            'bg-bg-tertiary hover:bg-bg-quaternary',
            'text-text-tertiary hover:text-text-secondary',
            'transition-colors duration-150',
            'disabled:opacity-50 disabled:cursor-not-allowed'
          )}
          title="Create folder"
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>

      {/* Context menu for folder options */}
      {contextMenu && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-50"
            onClick={closeContextMenu}
          />
          {/* Menu */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className={cn(
              'fixed z-50 py-1 rounded-lg',
              'bg-bg-secondary border border-bg-tertiary',
              'shadow-lg min-w-[140px]'
            )}
            style={{ left: contextMenu.x, top: contextMenu.y }}
          >
            <button
              onClick={() => {
                onEditFolder?.(contextMenu.folder);
                closeContextMenu();
              }}
              className={cn(
                'w-full flex items-center gap-2 px-3 py-2',
                'text-sm text-text-secondary hover:text-text-primary',
                'hover:bg-bg-tertiary transition-colors'
              )}
            >
              <Pencil className="w-4 h-4" />
              <span>Edit folder</span>
            </button>
            <button
              onClick={() => {
                onDeleteFolder?.(contextMenu.folder);
                closeContextMenu();
              }}
              className={cn(
                'w-full flex items-center gap-2 px-3 py-2',
                'text-sm text-error hover:bg-error/10',
                'transition-colors'
              )}
            >
              <Trash2 className="w-4 h-4" />
              <span>Delete folder</span>
            </button>
          </motion.div>
        </>
      )}
    </div>
  );
}

// Individual tab button component
interface TabButtonProps {
  label: string;
  icon?: React.ReactNode;
  emoji?: string;
  color?: string;
  isSelected: boolean;
  onClick: () => void;
  onContextMenu?: (e: React.MouseEvent) => void;
}

function TabButton({
  label,
  icon,
  emoji,
  color,
  isSelected,
  onClick,
  onContextMenu,
}: TabButtonProps) {
  return (
    <button
      onClick={onClick}
      onContextMenu={onContextMenu}
      className={cn(
        'flex-shrink-0 flex items-center gap-1.5',
        'px-3 py-1.5 rounded-full',
        'text-sm font-medium whitespace-nowrap',
        'transition-all duration-150',
        isSelected
          ? 'bg-purple-primary text-white'
          : 'bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary hover:text-text-primary'
      )}
      style={
        isSelected && color
          ? { backgroundColor: color }
          : undefined
      }
    >
      {/* Icon or emoji */}
      {icon && <span className={cn(isSelected ? 'text-white' : 'text-text-tertiary')}>{icon}</span>}
      {emoji && <span>{emoji}</span>}

      {/* Label */}
      <span>{label}</span>
    </button>
  );
}

// Loading skeleton for folder tabs
export function FolderTabsSkeleton() {
  return (
    <div className="flex items-center gap-2">
      <div className="h-8 w-12 rounded-full bg-bg-tertiary animate-pulse" />
      <div className="h-8 w-20 rounded-full bg-bg-tertiary animate-pulse" />
      <div className="h-8 w-16 rounded-full bg-bg-tertiary animate-pulse" />
      <div className="h-8 w-24 rounded-full bg-bg-tertiary animate-pulse" />
    </div>
  );
}
