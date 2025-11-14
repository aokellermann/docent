'use client';

import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export function CollectionTablePagination({
  page,
  pageSize,
  totalItems,
  setPage,
  containerClassName,
}: {
  page: number;
  pageSize: number;
  totalItems: number;
  setPage: (page: number) => void;
  containerClassName?: string;
}) {
  const totalPages = Math.ceil(totalItems / pageSize);
  const startItem = (page - 1) * pageSize + 1;
  const endItem = Math.min(page * pageSize, totalItems);

  return (
    <div className={cn('flex items-center gap-3', containerClassName)}>
      <span className="text-xs text-muted-foreground">
        {startItem}-{endItem} of {totalItems}
      </span>
      <div className="flex items-center gap-0.5">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setPage(page - 1)}
          disabled={page === 1}
          className="h-7 w-7 text-muted-foreground hover:text-primary disabled:opacity-30"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setPage(page + 1)}
          disabled={page >= totalPages}
          className="h-7 w-7 text-muted-foreground hover:text-primary disabled:opacity-30"
        >
          <ChevronRight className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}
