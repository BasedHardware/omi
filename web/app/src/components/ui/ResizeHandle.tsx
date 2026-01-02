'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';

interface ResizeHandleProps {
  onResize: (delta: number) => void;
  onResizeEnd?: () => void;
  onDoubleClick?: () => void;
  className?: string;
}

export function ResizeHandle({
  onResize,
  onResizeEnd,
  onDoubleClick,
  className,
}: ResizeHandleProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const startXRef = useRef(0);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
    startXRef.current = e.clientX;
  }, []);

  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!isDragging) return;
      const delta = e.clientX - startXRef.current;
      startXRef.current = e.clientX;
      onResize(delta);
    },
    [isDragging, onResize]
  );

  const handleMouseUp = useCallback(() => {
    if (isDragging) {
      setIsDragging(false);
      onResizeEnd?.();
    }
  }, [isDragging, onResizeEnd]);

  // Global mouse events for drag
  useEffect(() => {
    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';

      return () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      };
    }
  }, [isDragging, handleMouseMove, handleMouseUp]);

  return (
    <div
      onMouseDown={handleMouseDown}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onDoubleClick={onDoubleClick}
      className={cn(
        'relative w-1 cursor-col-resize group',
        'flex items-center justify-center',
        className
      )}
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize panel"
    >
      {/* Wider hit area */}
      <div className="absolute inset-y-0 -left-1.5 -right-1.5" />

      {/* Visible handle line */}
      <div
        className={cn(
          'w-0.5 h-full transition-all duration-150',
          isDragging
            ? 'bg-purple-primary'
            : isHovered
            ? 'bg-purple-primary/50'
            : 'bg-bg-quaternary'
        )}
      />

      {/* Grip dots - visible on hover */}
      <div
        className={cn(
          'absolute top-1/2 -translate-y-1/2',
          'flex flex-col gap-1 transition-opacity duration-150',
          isHovered || isDragging ? 'opacity-100' : 'opacity-0'
        )}
      >
        {[...Array(3)].map((_, i) => (
          <div
            key={i}
            className={cn(
              'w-1 h-1 rounded-full',
              isDragging ? 'bg-purple-primary' : 'bg-purple-primary/60'
            )}
          />
        ))}
      </div>
    </div>
  );
}
