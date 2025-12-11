'use client';

import { ListFilter, MessageSquare, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

export type CommentTab = 'inline' | 'list';

interface CommentSidebarHeaderProps {
  isCollapsed: boolean;
  onToggleCollapsed: () => void;
  activeTab: CommentTab;
  onTabChange: (tab: CommentTab) => void;
  showAllTranscripts: boolean;
  onSetShowAllTranscripts: (value: boolean) => void;
  commentCount: number;
}

export const CommentSidebarHeader = ({
  isCollapsed,
  onToggleCollapsed,
  activeTab,
  onTabChange,
  showAllTranscripts,
  onSetShowAllTranscripts,
  commentCount,
}: CommentSidebarHeaderProps) => {
  return (
    <div
      className={cn(
        'flex h-full bg-background p-3 pb-0 pr-0',
        !isCollapsed ? 'border-b justify-between' : 'justify-end'
      )}
    >
      {!isCollapsed && (
        <div className="flex items-end gap-4 flex-1">
          <button
            onClick={() => onTabChange('inline')}
            className={cn(
              'text-sm font-medium pb-1 border-b-2 transition-colors',
              activeTab === 'inline'
                ? 'border-primary text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            )}
          >
            Inline
          </button>
          <button
            onClick={() => onTabChange('list')}
            className={cn(
              'text-sm font-medium pb-1 border-b-2 transition-colors',
              activeTab === 'list'
                ? 'border-primary text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            )}
          >
            List
          </button>
        </div>
      )}
      <div className="flex pb-1 items-center gap-2">
        {!isCollapsed && activeTab === 'list' && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="size-6 flex items-center justify-center"
              >
                <ListFilter className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuRadioGroup
                value={showAllTranscripts ? 'all' : 'current'}
                onValueChange={(value) =>
                  onSetShowAllTranscripts(value === 'all')
                }
              >
                <DropdownMenuRadioItem value="current">
                  Current transcript
                </DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="all">
                  All transcripts
                </DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
            </DropdownMenuContent>
          </DropdownMenu>
        )}

        {!isCollapsed ? (
          <button
            onClick={onToggleCollapsed}
            className="size-6 flex items-center justify-center rounded hover:bg-accent transition-colors text-muted-foreground"
            aria-label={isCollapsed ? 'Expand comments' : 'Collapse comments'}
          >
            <X className="h-4 w-4" />
          </button>
        ) : (
          <button
            onClick={onToggleCollapsed}
            className="px-2 py-1 flex items-center gap-2  text-xs border border-border  rounded-md hover:bg-accent transition-colors text-muted-foreground"
            aria-label={isCollapsed ? 'Expand comments' : 'Collapse comments'}
          >
            <MessageSquare className="h-4 w-4" /> Comments
            {commentCount > 0 && (
              <span className="bg-muted px-1.5 py-0.5 rounded-full text-xs font-medium">
                {commentCount}
              </span>
            )}
          </button>
        )}
      </div>
    </div>
  );
};
