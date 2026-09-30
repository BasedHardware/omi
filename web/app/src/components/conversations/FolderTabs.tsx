'use client';

import { useRef, useState } from 'react';
import { Plus, Star, Pencil, Trash2, Inbox, Briefcase, Heart, Users } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Folder } from '@/types/folder';
import { OpenSurface } from '@/components/ui/OpenSurface';

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
  const [contextMenu, setContextMenu] = useState<{
    folder: Folder;
    x: number;
    y: number;
  } | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  const handleContextMenu = (e: React.MouseEvent, folder: Folder) => {
    e.preventDefault();
    setContextMenu({ folder, x: e.clientX, y: e.clientY });
    setMenuOpen(true);
  };

  const closeContextMenu = () => setMenuOpen(false);

  return (
    <div className="relative">
      {/* Tabs scroll sideways on phones and wrap on wider screens, where there
          is room for the second line they used to force. */}
      <div
        ref={scrollRef}
        className="no-scrollbar -mx-4 flex items-center gap-2 overflow-x-auto px-4 lg:mx-0 lg:flex-wrap lg:overflow-visible lg:px-0"
      >
        {/* All tab - always first */}
        <TabButton
          label="All"
          icon={<Inbox className="h-3.5 w-3.5" />}
          isSelected={selectedFolderId === FOLDER_ALL}
          onClick={() => onSelectFolder(FOLDER_ALL)}
        />

        {/* Starred tab - always second */}
        <TabButton
          label="Starred"
          icon={<Star className="h-3.5 w-3.5" />}
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
            'flex flex-shrink-0 items-center justify-center',
            'h-8 w-8 rounded-full',
            'bg-bg-tertiary hover:bg-bg-quaternary',
            'text-text-tertiary hover:text-text-secondary',
            'transition-colors duration-150',
            'disabled:cursor-not-allowed disabled:opacity-50',
          )}
          title="Create folder"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>

      {/* Context menu for folder options */}
      {contextMenu && menuOpen && (
        <div className="fixed inset-0 z-50" onClick={closeContextMenu} />
      )}
      {contextMenu && (
        <OpenSurface
          open={menuOpen}
          onExited={() => setContextMenu(null)}
          data-origin="top-left"
          className={cn(
            't-dropdown',
            'fixed z-50 rounded-lg py-1',
            'border border-bg-tertiary bg-bg-secondary',
            'min-w-[140px] shadow-lg',
          )}
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <button
            onClick={() => {
              onEditFolder?.(contextMenu.folder);
              closeContextMenu();
            }}
            className={cn(
              'flex w-full items-center gap-2 px-3 py-2',
              'text-sm text-text-secondary hover:text-text-primary',
              'transition-colors hover:bg-bg-tertiary',
            )}
          >
            <Pencil className="h-4 w-4" />
            <span>Edit folder</span>
          </button>
          <button
            onClick={() => {
              onDeleteFolder?.(contextMenu.folder);
              closeContextMenu();
            }}
            className={cn(
              'flex w-full items-center gap-2 px-3 py-2',
              'text-sm text-error hover:bg-error/10',
              'transition-colors',
            )}
          >
            <Trash2 className="h-4 w-4" />
            <span>Delete folder</span>
          </button>
        </OpenSurface>
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
        'flex flex-shrink-0 items-center gap-1.5',
        'rounded-full px-3 py-1.5',
        'whitespace-nowrap text-sm font-medium',
        'transition-all duration-150',
        isSelected
          ? 'bg-text-primary text-bg-primary'
          : 'bg-bg-tertiary text-text-secondary hover:bg-bg-quaternary hover:text-text-primary',
      )}
      style={isSelected && color ? { backgroundColor: color } : undefined}
    >
      {/* Icon or emoji */}
      {icon && (
        <span className={cn(isSelected ? 'text-bg-primary' : 'text-text-tertiary')}>
          {icon}
        </span>
      )}
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
      <div className="h-8 w-12 animate-pulse rounded-full bg-bg-tertiary" />
      <div className="h-8 w-20 animate-pulse rounded-full bg-bg-tertiary" />
      <div className="h-8 w-16 animate-pulse rounded-full bg-bg-tertiary" />
      <div className="h-8 w-24 animate-pulse rounded-full bg-bg-tertiary" />
    </div>
  );
}
