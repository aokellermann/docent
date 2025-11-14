import React, { useState } from 'react';
import { Copy, Check, ChevronDown, ChevronRight } from 'lucide-react';

import { BaseMetadata } from '@/app/types/transcriptTypes';
import { computeIntervalsForJsonPattern } from '@/lib/citationMatch';
import { SegmentedText } from '@/lib/SegmentedText';
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from '@/components/ui/collapsible';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export const formatMetadataValue = (value: any): string => {
  if (value === null || value === undefined) return 'N/A';
  if (typeof value === 'object') return JSON.stringify(value, null, 2);
  return String(value);
};

const shouldCollapseByDefault = (value: any): boolean => {
  // Collapse objects and arrays
  if (typeof value === 'object' && value !== null) return true;
  // Collapse long strings (>200 characters)
  const stringValue = String(value);
  return stringValue.length > 200;
};

const copyToClipboard = async (text: string): Promise<boolean> => {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
};

const CopyButton: React.FC<{ value: any }> = ({ value }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    const textToCopy = formatMetadataValue(value);
    const success = await copyToClipboard(textToCopy);
    if (success) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <button
      onClick={handleCopy}
      className="ml-2 p-1 rounded hover:bg-muted transition-colors"
      title="Copy to clipboard"
    >
      {copied ? (
        <Check className="h-3 w-3 text-green-text" />
      ) : (
        <Copy className="h-3 w-3 text-muted-foreground hover:text-primary" />
      )}
    </button>
  );
};

export function MetadataBlock({
  metadata,
  citedKey,
  citedTextRange,
}: {
  metadata: BaseMetadata;
  citedKey?: string;
  citedTextRange?: string;
}) {
  const metadataEntries = Object.entries(metadata);

  // Initialize collapse state for each key based on smart default
  const [collapsedKeys, setCollapsedKeys] = useState<Record<string, boolean>>(
    () => {
      const initial: Record<string, boolean> = {};
      metadataEntries.forEach(([key, value]) => {
        initial[key] = shouldCollapseByDefault(value);
      });
      return initial;
    }
  );

  const toggleKey = (key: string) => {
    setCollapsedKeys((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const expandAll = () => {
    const newState: Record<string, boolean> = {};
    metadataEntries.forEach(([key]) => {
      newState[key] = false;
    });
    setCollapsedKeys(newState);
  };

  const collapseAll = () => {
    const newState: Record<string, boolean> = {};
    metadataEntries.forEach(([key]) => {
      newState[key] = true;
    });
    setCollapsedKeys(newState);
  };

  const shouldHighlightRow = (key: string) => {
    return citedKey ? key === citedKey : false;
  };

  const getHighlightedValue = (value: any, shouldHighlight: boolean) => {
    const formattedValue = formatMetadataValue(value);
    if (!shouldHighlight || !citedTextRange) {
      return <span>{formattedValue}</span>;
    }
    const intervals = computeIntervalsForJsonPattern(
      formattedValue,
      citedTextRange
    );
    return <SegmentedText text={formattedValue} intervals={intervals} />;
  };

  return (
    <div className="space-y-2">
      {/* Bulk controls - only show if there are collapsible items */}
      <div className="flex gap-2 justify-end">
        <Button
          variant="ghost"
          size="sm"
          onClick={expandAll}
          className="h-7 text-xs px-2"
        >
          Expand All
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={collapseAll}
          className="h-7 text-xs px-2"
        >
          Collapse All
        </Button>
      </div>

      {/* Metadata rows */}
      <div className="bg-secondary rounded-lg border border-border overflow-hidden">
        <div className="divide-y divide-border">
          {metadataEntries.map(([key, value]) => {
            const isHighlightedRow = shouldHighlightRow(key);
            const isCollapsed = collapsedKeys[key];

            return (
              <Collapsible
                key={key}
                open={!isCollapsed}
                onOpenChange={() => toggleKey(key)}
              >
                <div
                  className={cn(
                    'transition-colors',
                    isHighlightedRow && 'bg-yellow-100 dark:bg-yellow-900/30'
                  )}
                  data-highlighted={isHighlightedRow ? 'true' : undefined}
                >
                  {/* Trigger - shows key, icon, and copy button */}
                  <CollapsibleTrigger asChild>
                    <div className="flex items-center p-2 hover:bg-muted/50 cursor-pointer">
                      <div className="flex items-center gap-1 flex-1 min-w-0">
                        {isCollapsed ? (
                          <ChevronRight className="h-3 w-3 text-muted-foreground flex-shrink-0" />
                        ) : (
                          <ChevronDown className="h-3 w-3 text-muted-foreground flex-shrink-0" />
                        )}
                        <span className="font-medium text-sm text-primary break-words">
                          {key}
                        </span>
                      </div>
                      <CopyButton value={value} />
                    </div>
                  </CollapsibleTrigger>

                  {/* Content - shows the value */}
                  <CollapsibleContent>
                    <div className="px-2 pb-2 pl-6">
                      <div className="text-sm text-muted-foreground break-words whitespace-pre-wrap font-mono text-xs">
                        {getHighlightedValue(value, isHighlightedRow)}
                      </div>
                    </div>
                  </CollapsibleContent>
                </div>
              </Collapsible>
            );
          })}
        </div>
      </div>
    </div>
  );
}
