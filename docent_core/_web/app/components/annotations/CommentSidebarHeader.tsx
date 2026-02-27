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
        'inline-flex items-center rounded-md border border-border bg-background p-1',
        !isCollapsed ? 'gap-1.5' : 'justify-end'
      )}
    >
      {!isCollapsed && (
        <div className="flex items-center gap-2">
          <button
            onClick={() => onTabChange('inline')}
            className={cn(
              'text-[11px] font-medium px-0.5 pb-0.5 border-b-2 transition-colors leading-none',
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
              'text-[11px] font-medium px-0.5 pb-0.5 border-b-2 transition-colors leading-none',
              activeTab === 'list'
                ? 'border-primary text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            )}
          >
            List
          </button>
        </div>
      )}
      <div className="flex items-center gap-0.5 shrink-0">
        {!isCollapsed && activeTab === 'list' && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="size-6 flex items-center justify-center"
              >
                <ListFilter className="h-3.5 w-3.5" />
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
            <X className="h-3.5 w-3.5" />
          </button>
        ) : (
          <button
            onClick={onToggleCollapsed}
            className="px-1.5 py-0.5 flex items-center gap-1.5 text-[11px] border border-border rounded-md hover:bg-accent transition-colors text-muted-foreground leading-none"
            aria-label={isCollapsed ? 'Expand comments' : 'Collapse comments'}
          >
            <MessageSquare className="h-3.5 w-3.5" /> Comments
            {commentCount > 0 && (
              <span className="bg-muted px-1 py-0.5 rounded-full text-[10px] font-medium leading-none">
                {commentCount}
              </span>
            )}
          </button>
        )}
      </div>
    </div>
  );
};
