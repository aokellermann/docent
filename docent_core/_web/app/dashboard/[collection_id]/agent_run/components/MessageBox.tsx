import React, { useCallback, useMemo } from 'react';

import { useAppSelector } from '@/app/store/hooks';
import { ChatMessage, Content, ToolCall } from '@/app/types/transcriptTypes';
import { cn } from '@/lib/utils';
import { Citation } from '@/app/types/experimentViewerTypes';
import { computeCitationIntervals } from '@/lib/citationMatch';

function stringify(x: any): string {
  if (typeof x === 'string') return x;
  return JSON.stringify(x);
}

// Helper function to detect if content contains JSON
export const hasJsonContent = (text: string): boolean => {
  try {
    const trimmed = text.trim();
    // Check if it looks like JSON (starts with { or [)
    if (
      (trimmed.startsWith('{') && trimmed.endsWith('}')) ||
      (trimmed.startsWith('[') && trimmed.endsWith(']'))
    ) {
      JSON.parse(trimmed);
      return true;
    }
  } catch (e) {
    // If parsing fails, it's not valid JSON
  }
  return false;
};

export function MessageBox({
  message,
  index,
  blockId: id,
  isHighlighted,
  citedRanges,
  prettyPrintJsonMessages,
  setPrettyPrintJsonMessages,
}: {
  message: ChatMessage;
  index: number;
  blockId?: string;
  isHighlighted: boolean;
  citedRanges: Citation[];
  prettyPrintJsonMessages: Set<number>;
  setPrettyPrintJsonMessages: React.Dispatch<React.SetStateAction<Set<number>>>;
}) {
  const highlightedCitationId = useAppSelector(
    (state) => state.transcript.highlightedCitationId
  );

  // Helper functions for tool call formatting (DRY) - memoized to avoid dependency issues
  const formatToolCallArgs = useCallback(
    (args: Record<string, unknown> | undefined) =>
      Object.entries(args || {})
        .map(([k, v]) => `${k}=${stringify(v)}`)
        .join(', '),
    []
  );

  const getToolCallLLMFormat = useCallback(
    (tool: ToolCall) =>
      tool.view
        ? `\n<tool call>\n${tool.view.content}\n</tool call>`
        : `\n<tool call>\n${tool.function}(${formatToolCallArgs(tool.arguments)})\n</tool call>`,
    [formatToolCallArgs]
  );

  const getToolCallDisplayContent = useCallback(
    (tool: ToolCall) =>
      tool.view
        ? tool.view.content
        : `${tool.function}(${formatToolCallArgs(tool.arguments)})`,
    [formatToolCallArgs]
  );

  // Helper function to render text with citation highlights (simpler version for tool calls)
  const renderTextWithHighlights = (
    text: string,
    intervals: { start: number; end: number; id: string }[]
  ) => {
    if (!intervals.length) return text;

    const parts: JSX.Element[] = [];
    let lastIndex = 0;

    // Sort intervals by start position
    const sortedIntervals = [...intervals].sort((a, b) => a.start - b.start);

    sortedIntervals.forEach((interval, i) => {
      // Add text before highlight
      if (interval.start > lastIndex) {
        parts.push(
          <span key={`text-${i}`}>{text.slice(lastIndex, interval.start)}</span>
        );
      }

      // Add highlighted text
      const highlightedText = text.slice(interval.start, interval.end);
      parts.push(
        <span
          key={`highlight-${i}`}
          className={cn(
            'px-0.5 py-0.25 rounded transition-colors',
            getCitationColors(
              message.role,
              interval.id === highlightedCitationId
            )
          )}
        >
          {highlightedText}
        </span>
      );

      lastIndex = interval.end;
    });

    // Add remaining text
    if (lastIndex < text.length) {
      parts.push(<span key="text-end">{text.slice(lastIndex)}</span>);
    }

    return <>{parts}</>;
  };

  // Helper function to extract text content from message content for citation matching
  // This includes tool calls in the same format as shown to LLMs, but only for citation matching
  const getMessageContentForCitations = useCallback(
    (message: ChatMessage): string => {
      let textContent = '';

      if (typeof message.content === 'string') {
        textContent = message.content;
      } else {
        textContent = message.content
          .filter(
            (item): item is Content & { text: string } =>
              item.type === 'text' && typeof item.text === 'string'
          )
          .map((item) => item.text)
          .join('\n');
      }

      if (
        message?.role === 'assistant' &&
        'tool_calls' in message &&
        message.tool_calls
      ) {
        for (const toolCall of message.tool_calls) {
          textContent += getToolCallLLMFormat(toolCall);
        }
      }

      return textContent;
    },
    [getToolCallLLMFormat]
  );

  // Helper function to extract text content from message content for display (no tool calls)
  const getMessageContent = (content: string | Content[]): string => {
    if (typeof content === 'string') {
      return content;
    }
    // If content is an array of Content objects
    return content
      .filter(
        (item): item is Content & { text: string } =>
          item.type === 'text' && typeof item.text === 'string'
      )
      .map((item) => item.text)
      .join('\n');
  };

  // Helper function to create character position mapping between original and pretty-printed JSON
  const createPositionMapping = (originalText: string, prettyText: string) => {
    // Create a mapping from original positions to pretty positions by finding matching content
    const originalToPretty: number[] = new Array(originalText.length);
    const prettyToOriginal: number[] = new Array(prettyText.length);

    let originalPos = 0;
    let prettyPos = 0;

    while (originalPos < originalText.length && prettyPos < prettyText.length) {
      const originalChar = originalText[originalPos];
      const prettyChar = prettyText[prettyPos];

      if (originalChar === prettyChar) {
        // Exact match - record the mapping
        originalToPretty[originalPos] = prettyPos;
        prettyToOriginal[prettyPos] = originalPos;
        originalPos++;
        prettyPos++;
      } else if (/\s/.test(originalChar) && /\s/.test(prettyChar)) {
        // Both are whitespace - advance both but prefer the pretty position mapping
        originalToPretty[originalPos] = prettyPos;
        prettyToOriginal[prettyPos] = originalPos;
        originalPos++;
        prettyPos++;
      } else if (/\s/.test(prettyChar)) {
        // Pretty has extra whitespace (common in formatted JSON)
        prettyToOriginal[prettyPos] = originalPos;
        prettyPos++;
      } else if (/\s/.test(originalChar)) {
        // Original has whitespace that was removed/changed
        originalToPretty[originalPos] = prettyPos;
        originalPos++;
      } else {
        // Non-matching characters - this shouldn't happen with valid JSON formatting
        originalToPretty[originalPos] = prettyPos;
        prettyToOriginal[prettyPos] = originalPos;
        originalPos++;
        prettyPos++;
      }
    }

    // Fill in any remaining positions
    while (originalPos < originalText.length) {
      originalToPretty[originalPos] = prettyText.length;
      originalPos++;
    }
    while (prettyPos < prettyText.length) {
      prettyToOriginal[prettyPos] = originalText.length;
      prettyPos++;
    }

    return { originalToPrety: originalToPretty, prettyToOriginal };
  };

  // Helper function to transform citation intervals from original to pretty-printed positions
  const transformCitationIntervals = (
    intervals: { start: number; end: number; id: string }[],
    originalText: string,
    prettyText: string
  ) => {
    if (originalText === prettyText) {
      return intervals; // No transformation needed
    }

    const { originalToPrety } = createPositionMapping(originalText, prettyText);

    return intervals
      .map((interval) => {
        // Map the start and end positions
        const newStart = originalToPrety[interval.start] ?? interval.start;
        const newEnd = originalToPrety[interval.end - 1] ?? interval.end;

        return {
          ...interval,
          start: newStart,
          end: newEnd + 1, // Add 1 back since we mapped end-1
        };
      })
      .filter((interval) => interval.start < interval.end); // Remove invalid intervals
  };

  // Helper function to detect and pretty-print JSON
  const formatContent = (text: string): string => {
    if (!prettyPrintJsonMessages.has(index)) {
      return text;
    }

    // Try to parse as JSON and pretty-print if successful
    try {
      const trimmed = text.trim();
      // Check if it looks like JSON (starts with { or [)
      if (
        (trimmed.startsWith('{') && trimmed.endsWith('}')) ||
        (trimmed.startsWith('[') && trimmed.endsWith(']'))
      ) {
        const parsed = JSON.parse(trimmed);
        return JSON.stringify(parsed, null, 2);
      }
    } catch (e) {
      // If parsing fails, return original text
    }
    return text;
  };

  // Memoize citation intervals computation for all messages with citations
  const allCitationIntervals = useMemo(() => {
    const messageContent = getMessageContentForCitations(message);
    return computeCitationIntervals(messageContent, citedRanges);
  }, [message, citedRanges, getMessageContentForCitations]);

  const getRoleStyle = (role: string, isHighlighted: boolean) => {
    const transitionClasses = 'transition-colors duration-500 ease-out';

    // Use specific color classes instead of dynamic ones
    const getColorClasses = (role: string, highlighted: boolean) => {
      switch (role) {
        case 'user':
          return highlighted
            ? 'bg-muted-foreground/40 border-l-4 border-muted-foreground'
            : 'bg-gray-50 dark:bg-gray-900/50 border-l-4 border-gray-300 dark:border-gray-700';
        case 'assistant':
          return highlighted
            ? 'bg-blue-500/40 border-l-4 border-blue-500'
            : 'bg-blue-50 dark:bg-blue-950/30 border-l-4 border-blue-300 dark:border-blue-700';
        case 'system':
          return highlighted
            ? 'bg-orange-500/40 border-l-4 border-orange-500'
            : 'bg-orange-50 dark:bg-orange-950/30 border-l-4 border-orange-300 dark:border-orange-700';
        case 'tool':
          return highlighted
            ? 'bg-green-500/40 border-l-4 border-green-500'
            : 'bg-green-50 dark:bg-green-950/30 border-l-4 border-green-300 dark:border-green-700';
        default:
          return highlighted
            ? 'bg-slate-500/40 border-l-4 border-slate-500'
            : 'bg-gray-50 dark:bg-gray-900/50 border-l-4 border-gray-300 dark:border-gray-700';
      }
    };

    const colorClasses = getColorClasses(role, isHighlighted);
    return `${colorClasses} ${transitionClasses}`;
  };

  const getCitationColors = (role: string, isHighlighted: boolean) => {
    switch (role) {
      case 'user':
        return isHighlighted
          ? 'bg-muted-foreground text-background'
          : 'bg-muted-foreground/20';
      case 'assistant':
        return isHighlighted ? 'bg-blue-600 text-white' : 'bg-blue-500/20';
      case 'system':
        return isHighlighted ? 'bg-orange-600 text-white' : 'bg-orange-500/20';
      case 'tool':
        return isHighlighted ? 'bg-green-600 text-white' : 'bg-green-500/20';
      default:
        return isHighlighted ? 'bg-slate-600 text-white' : 'bg-slate-500/20';
    }
  };

  const renderMessageContent = (
    content: string | Content[],
    citations: Citation[],
    role: string,
    precomputedIntervals: { start: number; end: number; id: string }[]
  ) => {
    // First apply JSON pretty-printing if enabled, then get the final content string
    const rawContentString = getMessageContent(content);
    const contentString = prettyPrintJsonMessages.has(index)
      ? formatContent(rawContentString)
      : rawContentString;

    if (!citations || citations.length === 0) {
      return <div>{contentString}</div>;
    }

    const textLength = contentString.length;
    type EventMap = Record<number, string[]>;
    const opens: EventMap = {};
    const closes: EventMap = {};

    // If content was pretty-printed, transform the citation intervals to match the new positions
    // Otherwise use the precomputed intervals
    let citationIntervals: { start: number; end: number; id: string }[];
    if (
      prettyPrintJsonMessages.has(index) &&
      rawContentString !== contentString
    ) {
      // Transform intervals from original positions to pretty-printed positions
      citationIntervals = transformCitationIntervals(
        precomputedIntervals,
        rawContentString,
        contentString
      );
    } else {
      // Use precomputed intervals
      citationIntervals = precomputedIntervals;
    }

    // Build sweep events from the citation intervals
    citationIntervals.forEach(({ start, end, id }) => {
      if (start >= end) return;
      if (!opens[start]) opens[start] = [];
      if (!closes[end]) closes[end] = [];
      opens[start].push(id);
      closes[end].push(id);
    });

    const boundaries = new Set<number>([0, textLength]);
    Object.keys(opens).forEach((k) => boundaries.add(Number(k)));
    Object.keys(closes).forEach((k) => boundaries.add(Number(k)));
    const sorted = Array.from(boundaries).sort((a, b) => a - b);

    const parts: (string | JSX.Element)[] = [];
    const active = new Set<string>();

    for (let i = 0; i < sorted.length - 1; i++) {
      const idx = sorted[i];
      const next = sorted[i + 1];

      // Apply closes then opens at the boundary
      (closes[idx] || []).forEach((id) => active.delete(id));
      (opens[idx] || []).forEach((id) => active.add(id));

      if (next <= idx) continue;
      const slice = contentString.slice(idx, next);
      if (!slice) continue;

      if (active.size === 0) {
        parts.push(slice);
      } else {
        const isHighlighted = highlightedCitationId
          ? Array.from(active).includes(highlightedCitationId)
          : false;
        parts.push(
          <span
            key={`seg-${idx}-${next}`}
            className={getCitationColors(role, isHighlighted)}
            data-citation-ids={Array.from(active).join(',')}
          >
            {slice}
          </span>
        );
      }
    }

    return <div>{parts}</div>;
  };

  // Add a new function to extract reasoning content
  const getReasoningContent = (content: string | Content[]): string | null => {
    if (typeof content === 'string') {
      return null;
    }
    // Find the first reasoning content item
    const reasoningItem = content.find(
      (item): item is Content & { reasoning: string } =>
        item.type === 'reasoning' && typeof item.reasoning === 'string'
    );
    return reasoningItem ? reasoningItem.reasoning : null;
  };

  // Helper to render tool-specific information
  const renderToolInfo = () => {
    if (message.role === 'tool') {
      return (
        <div className="mt-1 text-[10px] text-muted-foreground">
          {message.tool_call_id && (
            <span>Tool Call ID: {message.tool_call_id}</span>
          )}
          {message.function && (
            <span className="ml-2">Function: {message.function}</span>
          )}
          {message.error && (
            <div className="mt-1 text-destructive">
              Error: {message.error.message}
            </div>
          )}
        </div>
      );
    }
    return null;
  };

  // Helper to render tool calls with citation highlighting for assistant messages
  const renderToolCalls = () => {
    if (message.role === 'assistant' && message.tool_calls) {
      // Calculate the offset where tool calls start in the citation content
      const mainContentLength = getMessageContent(message.content).length;

      return message.tool_calls.map((tool, i) => {
        // Calculate the start position of this tool call in the full citation content
        let toolCallStartOffset = mainContentLength;

        // Add the length of previous tool calls
        for (let j = 0; j < i; j++) {
          const prevTool = message.tool_calls![j];
          toolCallStartOffset += getToolCallLLMFormat(prevTool).length;
        }

        // Get the tool call content in LLM format
        const toolCallContent = getToolCallLLMFormat(tool);

        const toolCallEndOffset = toolCallStartOffset + toolCallContent.length;

        // Find citation intervals that overlap with this tool call
        const toolCallIntervals = allCitationIntervals
          .filter(
            (interval) =>
              interval.start < toolCallEndOffset &&
              interval.end > toolCallStartOffset
          )
          .map((interval) => ({
            ...interval,
            // Adjust positions relative to the tool call content
            start: Math.max(0, interval.start - toolCallStartOffset),
            end: Math.min(
              toolCallContent.length,
              interval.end - toolCallStartOffset
            ),
          }))
          .filter((interval) => interval.start < interval.end);

        // Extract just the inner content (without the <tool call> wrapper for display)
        const displayContent = getToolCallDisplayContent(tool);

        // Adjust intervals to match display content (subtract the "<tool call>\n" prefix)
        const prefixLength = '\n<tool call>\n'.length;
        const adjustedIntervals = toolCallIntervals
          .map((interval) => ({
            ...interval,
            start: Math.max(0, interval.start - prefixLength),
            end: Math.min(displayContent.length, interval.end - prefixLength),
          }))
          .filter(
            (interval) =>
              interval.start < interval.end &&
              interval.start < displayContent.length
          );

        return (
          <div
            key={i}
            className="mt-1 p-1.5 bg-secondary/85 rounded text-xs break-all whitespace-pre-wrap"
          >
            <div className="text-[10px] text-muted-foreground mb-0.5">
              Tool Call ID: {tool.id}
            </div>
            {tool.view ? (
              <span className="font-mono">
                {adjustedIntervals.length > 0
                  ? renderTextWithHighlights(displayContent, adjustedIntervals)
                  : displayContent}
              </span>
            ) : (
              <div className="font-mono">
                <span className="font-semibold">{tool.function}</span>
                <span className="text-muted-foreground">
                  (
                  {adjustedIntervals.length > 0
                    ? renderTextWithHighlights(
                        formatToolCallArgs(tool.arguments),
                        adjustedIntervals
                          .map((interval) => {
                            // Adjust for the function name and opening parenthesis
                            const functionPrefixLength =
                              tool.function.length + 1; // +1 for "("
                            return {
                              ...interval,
                              start: Math.max(
                                0,
                                interval.start - functionPrefixLength
                              ),
                              end: Math.max(
                                0,
                                interval.end - functionPrefixLength
                              ),
                            };
                          })
                          .filter(
                            (interval) =>
                              interval.start >= 0 &&
                              interval.end > interval.start
                          )
                      )
                    : formatToolCallArgs(tool.arguments)}
                  )
                </span>
              </div>
            )}
          </div>
        );
      });
    }
    return null;
  };

  return (
    <div className="mb-1">
      <div
        id={id}
        className={cn(
          'p-2 rounded-md text-sm',
          !isHighlighted && 'transition-all duration-1500',
          getRoleStyle(message.role, isHighlighted)
        )}
      >
        <div className="text-[10px] text-muted-foreground flex justify-between mb-1">
          <span>
            Block {index} |{' '}
            {message.role.charAt(0).toUpperCase() + message.role.slice(1)}
          </span>
          {hasJsonContent(getMessageContent(message.content)) && (
            <label className="flex items-center space-x-1 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={prettyPrintJsonMessages.has(index)}
                onChange={(e) => {
                  setPrettyPrintJsonMessages((prev) => {
                    const newSet = new Set(prev);
                    if (e.target.checked) {
                      newSet.add(index);
                    } else {
                      newSet.delete(index);
                    }
                    return newSet;
                  });
                }}
                className="h-3 w-3 rounded border-border"
              />
              <span>Pretty JSON</span>
            </label>
          )}
        </div>

        {typeof message.content !== 'string' && (
          <>
            {message.role === 'assistant' &&
              getReasoningContent(message.content) && (
                <div className="mb-2 px-2 py-2 bg-muted border-l-2 border-border text-xs text-primary italic whitespace-pre-wrap [overflow-wrap:anywhere] max-w-full overflow-x-auto font-mono rounded custom-scrollbar">
                  {getReasoningContent(message.content)}
                </div>
              )}
          </>
        )}
        <div className="whitespace-pre-wrap [overflow-wrap:anywhere] max-w-full text-xs overflow-x-auto font-mono custom-scrollbar">
          {renderMessageContent(
            message.content,
            citedRanges,
            message.role,
            allCitationIntervals
          )}
        </div>
        {renderToolInfo()}
        {renderToolCalls()}
      </div>
    </div>
  );
}
