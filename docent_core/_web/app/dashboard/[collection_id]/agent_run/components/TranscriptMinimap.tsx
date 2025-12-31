'use client';

import React, { useMemo, useRef, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { ChatMessage } from '@/app/types/transcriptTypes';
import { Comment } from '@/app/api/labelApi';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { AlertTriangle, MessageSquare } from 'lucide-react';

// Color scheme matching MessageBox.tsx
const getRoleColor = (role: string): string => {
  switch (role) {
    case 'system':
      return 'bg-orange-400 dark:bg-orange-600';
    case 'user':
      return 'bg-gray-400 dark:bg-gray-500';
    case 'assistant':
      return 'bg-blue-400 dark:bg-blue-600';
    case 'tool':
      return 'bg-green-400 dark:bg-green-600';
    default:
      return 'bg-gray-400 dark:bg-gray-500';
  }
};

interface MinimapBarProps {
  message: ChatMessage;
  index: number;
  isCurrent: boolean;
  hasComments: boolean;
  onClick: () => void;
}

const MinimapBar = React.forwardRef<HTMLButtonElement, MinimapBarProps>(
  ({ message, index, isCurrent, hasComments, onClick }, ref) => {
    const hasError =
      message.role === 'tool' && 'error' in message && message.error;

    // Build tooltip content
    const tooltipContent = useMemo(() => {
      const parts = [`Block ${index}`, message.role];
      if (hasError) parts.push('(error)');
      if (hasComments) parts.push('(comments)');
      return parts.join(' ');
    }, [index, message.role, hasError, hasComments]);

    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            ref={ref}
            onClick={onClick}
            className={cn(
              'relative h-full rounded-sm transition-all hover:opacity-80',
              'flex-1 min-w-[36px]', // Grow to fill space, but maintain minimum width
              getRoleColor(message.role),
              isCurrent && 'ring-2 ring-inset ring-primary'
            )}
            aria-label={tooltipContent}
          >
            {/* Icon indicators */}
            <div className="absolute inset-0 flex items-center justify-center gap-0.5">
              {hasError && (
                <AlertTriangle
                  className="w-3 h-3 text-red-700 dark:text-red-300 drop-shadow-sm"
                  fill="currentColor"
                  strokeWidth={2.5}
                />
              )}
              {hasComments && (
                <MessageSquare
                  className="w-3 h-3 text-cyan-700 dark:text-cyan-300 drop-shadow-sm"
                  fill="currentColor"
                  strokeWidth={2.5}
                />
              )}
            </div>
          </button>
        </TooltipTrigger>
        <TooltipContent side="bottom" align="center">
          <p className="text-xs">{tooltipContent}</p>
        </TooltipContent>
      </Tooltip>
    );
  }
);
MinimapBar.displayName = 'MinimapBar';

export interface TranscriptMinimapProps {
  messages: ChatMessage[];
  currentBlockIndex: number | null;
  blockIdxToCommentsMap: Record<number, Comment[]>;
  onBlockClick: (blockIdx: number) => void;
  className?: string;
}

export const TranscriptMinimap: React.FC<TranscriptMinimapProps> = ({
  messages,
  currentBlockIndex,
  blockIdxToCommentsMap,
  onBlockClick,
  className,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const barRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // Scroll to the current block when currentBlockIndex changes
  useEffect(() => {
    if (
      currentBlockIndex !== null &&
      containerRef.current &&
      barRefs.current[currentBlockIndex]
    ) {
      const container = containerRef.current;
      const bar = barRefs.current[currentBlockIndex];
      if (bar) {
        const containerRect = container.getBoundingClientRect();
        const barRect = bar.getBoundingClientRect();

        // Check if the bar is outside the visible area
        const barLeft =
          barRect.left - containerRect.left + container.scrollLeft;
        const barRight = barLeft + barRect.width;
        const visibleLeft = container.scrollLeft;
        const visibleRight = container.scrollLeft + containerRect.width;

        if (barLeft < visibleLeft || barRight > visibleRight) {
          // Scroll to center the bar in the container
          const scrollTarget =
            barLeft - containerRect.width / 2 + barRect.width / 2;
          container.scrollTo({
            left: Math.max(0, scrollTarget),
            behavior: 'smooth',
          });
        }
      }
    }
  }, [currentBlockIndex]);

  if (!messages || messages.length === 0) {
    return null;
  }

  return (
    <div className={className}>
      {/* Legend */}
      <div className="flex flex-wrap gap-x-1 gap-y-0.5 text-[10px] text-muted-foreground">
        {/* Title */}
        <span className="font-medium text-foreground">
          Minimap ({messages.length} messages)
        </span>
        {/* Separator */}
        <div className="w-px h-3 bg-border mx-1" />
        {/* Role colors */}
        <div className="flex items-center gap-1">
          <div className="w-2 h-2 rounded-sm bg-orange-400 dark:bg-orange-600" />
          <span>System</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-2 h-2 rounded-sm bg-gray-400 dark:bg-gray-500" />
          <span>User</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-2 h-2 rounded-sm bg-blue-400 dark:bg-blue-600" />
          <span>Assistant</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-2 h-2 rounded-sm bg-green-400 dark:bg-green-600" />
          <span>Tool</span>
        </div>
        {/* Separator */}
        <div className="w-px h-3 bg-border mx-1" />
        {/* Icon indicators */}
        <div className="flex items-center gap-1">
          <AlertTriangle
            className="w-2.5 h-2.5 text-red-700 dark:text-red-300"
            fill="currentColor"
          />
          <span>Error</span>
        </div>
        <div className="flex items-center gap-1">
          <MessageSquare
            className="w-2.5 h-2.5 text-cyan-700 dark:text-cyan-300"
            fill="currentColor"
          />
          <span>Comments</span>
        </div>
      </div>

      {/* Minimap bars container */}
      <div
        ref={containerRef}
        className="flex flex-nowrap gap-[2px] h-8 overflow-x-auto overflow-y-hidden custom-scrollbar py-1"
        role="navigation"
        aria-label="Transcript minimap navigation"
      >
        {messages.map((message, index) => (
          <MinimapBar
            key={index}
            ref={(el) => {
              barRefs.current[index] = el;
            }}
            message={message}
            index={index}
            isCurrent={currentBlockIndex === index}
            hasComments={!!blockIdxToCommentsMap[index]?.length}
            onClick={() => onBlockClick(index)}
          />
        ))}
      </div>
    </div>
  );
};

export default TranscriptMinimap;
