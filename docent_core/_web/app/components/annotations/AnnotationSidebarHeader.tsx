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

export type AnnotationTab = 'inline' | 'list';

interface AnnotationSidebarHeaderProps {
  isCollapsed: boolean;
  onToggleCollapsed: () => void;
  activeTab: AnnotationTab;
  onTabChange: (tab: AnnotationTab) => void;
  showAllTranscripts: boolean;
  onSetShowAllTranscripts: (value: boolean) => void;
}

export const AnnotationSidebarHeader = ({
  isCollapsed,
  onToggleCollapsed,
  activeTab,
  onTabChange,
  showAllTranscripts,
  onSetShowAllTranscripts,
}: AnnotationSidebarHeaderProps) => {
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
            {/* <div className="bg-muted px-1.5 rounded-full h-5">
              {inlineAnnotationCount}
            </div> */}
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
            {/* <div className="bg-muted px-1.5 rounded-full h-5">
              {listAnnotationCount}
            </div> */}
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
          </button>
        )}
      </div>
    </div>
  );
};
