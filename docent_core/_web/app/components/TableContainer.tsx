'use client';

import type {
  DragEvent as ReactDragEvent,
  ReactNode,
  UIEvent as ReactUIEvent,
} from 'react';

import { cn } from '@/lib/utils';

interface TableContainerProps {
  children: ReactNode;
  className?: string;
  scrollClassName?: string;
  scrollRef?: (node: HTMLDivElement | null) => void;
  onScroll?: (event: ReactUIEvent<HTMLDivElement>) => void;
  dropZoneHandlers?: {
    onDragOver: (event: ReactDragEvent<HTMLDivElement>) => void;
    onDragLeave: (event: ReactDragEvent<HTMLDivElement>) => void;
    onDrop: (event: ReactDragEvent<HTMLDivElement>) => void;
  };
  overlay?: ReactNode;
}

// Keeps DQL and filter tables visually consistent by centralizing the scrollable container layout.
export function TableContainer({
  children,
  className,
  scrollClassName,
  scrollRef,
  onScroll,
  dropZoneHandlers,
  overlay,
}: TableContainerProps) {
  return (
    <div
      className={cn(
        'border rounded-md flex-1 flex flex-col min-h-0 relative',
        className
      )}
    >
      <div
        className={cn(
          'flex-1 min-h-0 overflow-auto custom-scrollbar relative',
          scrollClassName
        )}
        ref={scrollRef}
        onScroll={onScroll}
        {...(dropZoneHandlers ?? {})}
      >
        {children}
        {overlay}
      </div>
    </div>
  );
}
