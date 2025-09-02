import {
  ChevronDown,
  ChevronUp,
  FileText,
  Loader2,
  Folder,
  FolderOpen,
  Maximize2,
  Minimize2,
  ChevronRight,
} from 'lucide-react';
import React, {
  forwardRef,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { useAppDispatch, useAppSelector } from '@/app/store/hooks';
import {
  addMatchedCitations,
  clearHighlightedCitation,
  selectAllCitations,
} from '@/app/store/transcriptSlice';
import {
  ChatMessage,
  Content,
  AgentRun,
  TranscriptGroup,
} from '@/app/types/transcriptTypes';
import { Card } from '@/components/ui/card';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';

import UuidPill from '@/components/UuidPill';
import { useDebounce } from '@/hooks/use-debounce';

import MetadataDialog from './MetadataDialog';
import { cn } from '@/lib/utils';
import { Citation } from '@/app/types/experimentViewerTypes';
import { computeCitationIntervals } from '@/lib/citationMatch';
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from '@/components/ui/resizable';

// Export interface for use in other components
export interface AgentRunViewerHandle {
  scrollToBlock: (
    blockIdx: number,
    transcriptIdx: number,
    agentRunIdx: number,
    highlightDuration?: number
  ) => void;
}

// Add props interface
interface AgentRunViewerProps {
  secondary: boolean;
  agentRun?: AgentRun;
  otherAgentRunRef?: React.RefObject<AgentRunViewerHandle>;
  initialTranscriptIdx?: number;
}

// Add this helper function near the top of the file
const formatMetadataValue = (value: any): string => {
  if (typeof value === 'object' && value !== null) {
    return JSON.stringify(value, null, 2);
  }
  return String(value);
};

// Helper function to sort transcripts by created_at timestamp
const sortTranscriptsByTimestamp = (
  transcriptIds: string[],
  transcripts: Record<string, any>
): string[] => {
  return [...transcriptIds].sort((a, b) => {
    const timestampA = transcripts[a].created_at;
    const timestampB = transcripts[b].created_at;
    if (!timestampA && !timestampB) return 0;
    if (!timestampA) return 1;
    if (!timestampB) return -1;
    return new Date(timestampA).getTime() - new Date(timestampB).getTime();
  });
};

// Interface for hierarchical transcript group structure
interface TranscriptGroupNode {
  group: TranscriptGroup;
  transcripts: string[];
  children: TranscriptGroupNode[];
  level: number;
}

// Component for rendering a single transcript group node (recursive)
const TranscriptGroupNode: React.FC<{
  node: TranscriptGroupNode;
  selectedTranscriptKey: string | null;
  selectedTranscriptGroupId: string | null;
  expandedGroups: Set<string>;
  onTranscriptSelect: (transcriptKey: string) => void;
  onGroupToggle: (groupId: string) => void;
  agentRun: AgentRun;
}> = ({
  node,
  selectedTranscriptKey,
  selectedTranscriptGroupId,
  expandedGroups,
  onTranscriptSelect,
  onGroupToggle,
  agentRun,
}) => {
  const isExpanded = expandedGroups.has(node.group.id);
  const isSelected = selectedTranscriptGroupId === node.group.id;
  const hasTranscripts = node.transcripts.length > 0;
  const hasChildren = node.children.length > 0;

  // Check if this group or any of its descendants contain transcripts
  const hasTranscriptsInSubtree = useMemo(() => {
    if (hasTranscripts) return true;

    const checkChildren = (children: TranscriptGroupNode[]): boolean => {
      return children.some((child) => {
        if (child.transcripts.length > 0) return true;
        return checkChildren(child.children);
      });
    };

    return checkChildren(node.children);
  }, [hasTranscripts, node.children]);

  return (
    <div className="space-y-1">
      {/* Group Header - only show if it has transcripts or children with transcripts */}
      {(hasTranscriptsInSubtree || hasChildren) && (
        <div
          className={cn(
            'flex items-center text-xs rounded border transition-colors min-w-0',
            isSelected
              ? 'bg-indigo-bg border-indigo-border text-primary'
              : hasTranscriptsInSubtree
                ? 'bg-muted/60 border-border/80 text-primary/80 hover:bg-muted hover:text-primary'
                : 'bg-muted/30 border-border/30 text-muted-foreground/80 hover:bg-muted/50 hover:text-muted-foreground'
          )}
          style={{ marginLeft: `${node.level * 12}px` }}
        >
          <button
            onClick={() => onGroupToggle(node.group.id)}
            className="flex items-center flex-1 px-2 py-1 min-w-0 cursor-pointer"
          >
            {isExpanded ? (
              <FolderOpen className="h-3 w-3 mr-1 flex-shrink-0" />
            ) : (
              <Folder className="h-3 w-3 mr-1 flex-shrink-0" />
            )}
            <span className="text-ellipsis whitespace-nowrap overflow-hidden min-w-0">
              {node.group.name || node.group.id}
            </span>
          </button>
          {Object.keys(node.group.metadata || {}).length > 0 && (
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="flex h-full items-center">
                  <MetadataDialog
                    metadata={node.group.metadata || {}}
                    title={`Transcript Group Metadata - ${node.group.name || node.group.id}`}
                    trigger={
                      <button
                        className={cn(
                          'p-0.5 mr-1 rounded transition-colors',
                          isSelected
                            ? 'hover:bg-indigo-bg text-primary'
                            : hasTranscriptsInSubtree
                              ? 'hover:bg-muted text-primary/80'
                              : 'hover:bg-muted/50 text-muted-foreground/80'
                        )}
                      >
                        <FileText className="h-3 w-3" />
                      </button>
                    }
                  />
                </div>
              </TooltipTrigger>
              <TooltipContent side="left" align="center">
                <p>View transcript group metadata</p>
              </TooltipContent>
            </Tooltip>
          )}
        </div>
      )}

      {/* Group Transcripts */}
      {isExpanded && (
        <div className="space-y-1">
          {node.transcripts.map((transcriptKey) => (
            <div
              key={transcriptKey}
              className={cn(
                'flex items-center text-xs rounded border transition-colors min-w-0 shadow-sm',
                selectedTranscriptKey === transcriptKey
                  ? 'bg-blue-bg border-blue-border text-primary shadow-md'
                  : 'bg-secondary border-border text-primary hover:bg-blue-bg/50 hover:border-blue-border/50'
              )}
              style={{ marginLeft: `${(node.level + 1) * 12}px` }}
            >
              <button
                onClick={() => onTranscriptSelect(transcriptKey)}
                className="flex-1 text-left px-2 py-1.5 text-ellipsis whitespace-nowrap overflow-hidden min-w-0 font-medium"
                title={transcriptKey}
              >
                {transcriptKey}
              </button>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex h-full items-center">
                    <MetadataDialog
                      metadata={
                        agentRun?.transcripts[transcriptKey]?.metadata || {}
                      }
                      title={`Transcript Metadata - ${transcriptKey}`}
                      trigger={
                        <button
                          className={cn(
                            'p-0.5 mr-1 rounded transition-colors',
                            selectedTranscriptKey === transcriptKey
                              ? 'hover:bg-blue-bg text-primary'
                              : 'hover:bg-accent text-muted-foreground'
                          )}
                        >
                          <FileText className="h-3 w-3" />
                        </button>
                      }
                    />
                  </div>
                </TooltipTrigger>
                <TooltipContent side="left" align="center">
                  <p>View transcript metadata</p>
                </TooltipContent>
              </Tooltip>
            </div>
          ))}
        </div>
      )}

      {/* Child Groups (recursive) */}
      {isExpanded &&
        node.children.map((childNode) => (
          <TranscriptGroupNode
            key={childNode.group.id}
            node={childNode}
            selectedTranscriptKey={selectedTranscriptKey}
            selectedTranscriptGroupId={selectedTranscriptGroupId}
            expandedGroups={expandedGroups}
            onTranscriptSelect={onTranscriptSelect}
            onGroupToggle={onGroupToggle}
            agentRun={agentRun}
          />
        ))}
    </div>
  );
};

// Helper function to detect if content contains JSON
const hasJsonContent = (text: string): boolean => {
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

// Helper function to get message content as string
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

// Helper function to build transcript path
const buildTranscriptPath = (
  transcriptKey: string,
  agentRun: AgentRun
): Array<{ id: string; name: string; type: 'group' | 'transcript' }> => {
  const path: Array<{
    id: string;
    name: string;
    type: 'group' | 'transcript';
  }> = [];

  if (!agentRun || !agentRun.transcripts[transcriptKey]) {
    return path;
  }

  const transcript = agentRun.transcripts[transcriptKey];
  const transcriptGroups = agentRun.transcript_groups || {};

  // Add the transcript itself at the end (use transcriptKey like in sidebar)
  path.unshift({
    id: transcriptKey,
    name: transcriptKey,
    type: 'transcript',
  });

  // Build the path from the transcript's group up to the root
  let currentGroupId = transcript.transcript_group_id;
  while (currentGroupId && transcriptGroups[currentGroupId]) {
    const group = transcriptGroups[currentGroupId];

    // Check if there are multiple groups with the same name in the same parent
    let displayName = group.name || currentGroupId;
    if (group.parent_transcript_group_id) {
      const siblings = Object.values(transcriptGroups).filter(
        (g) =>
          g.parent_transcript_group_id === group.parent_transcript_group_id &&
          g.name === group.name
      );

      if (siblings.length > 1) {
        // Sort siblings by created_at timestamp to match sidebar order
        const sortedSiblings = siblings.sort((a, b) => {
          const aTime = a.created_at ? new Date(a.created_at).getTime() : 0;
          const bTime = b.created_at ? new Date(b.created_at).getTime() : 0;
          return aTime - bTime;
        });

        const index = sortedSiblings.findIndex((g) => g.id === group.id);
        if (index >= 0) {
          displayName = `${displayName} - ${index + 1}`;
        }
      }
    }

    path.unshift({
      id: currentGroupId,
      name: displayName,
      type: 'group',
    });
    currentGroupId = group.parent_transcript_group_id || null;
  }

  return path;
};

// Component for displaying transcript path
const TranscriptPath: React.FC<{
  path: Array<{ id: string; name: string; type: 'group' | 'transcript' }>;
}> = ({ path }) => {
  if (path.length === 0) return null;

  return (
    <div className="flex items-center text-xs text-muted-foreground/70 mb-1 px-1 overflow-hidden">
      <div className="flex items-center space-x-0.5 min-w-0 flex-1 overflow-x-auto">
        {path.map((item, index) => (
          <React.Fragment key={item.id}>
            {index > 0 && (
              <ChevronRight className="h-2.5 w-2.5 text-muted-foreground/40 flex-shrink-0" />
            )}
            <span
              className={cn(
                'px-1 py-0.5 rounded text-xs whitespace-nowrap flex-shrink-0',
                item.type === 'group'
                  ? 'bg-muted/30 text-muted-foreground/80'
                  : 'bg-muted/40 text-muted-foreground'
              )}
            >
              {item.name}
            </span>
          </React.Fragment>
        ))}
      </div>
    </div>
  );
};

const AgentRunViewer = forwardRef<AgentRunViewerHandle, AgentRunViewerProps>(
  ({ secondary, agentRun, otherAgentRunRef, initialTranscriptIdx }, ref) => {
    const dispatch = useAppDispatch();
    agentRun = useAppSelector(
      (state) =>
        agentRun ||
        (secondary
          ? state.transcript.altAgentRun
          : state.transcript?.curAgentRun)
    );

    const allCitations = useAppSelector(selectAllCitations);

    // Add state for selected transcript key and transcript group
    const [selectedTranscriptKey, setSelectedTranscriptKey] = useState<
      string | null
    >(null);
    const [selectedTranscriptGroupId, setSelectedTranscriptGroupId] = useState<
      string | null
    >(null);
    const [expandedGroups, setExpandedGroups] = useState<Set<string>>(
      new Set()
    );
    const [prettyPrintJsonMessages, setPrettyPrintJsonMessages] = useState<
      Set<number>
    >(new Set());

    // Initialize expanded groups when transcript groups are available
    useEffect(() => {
      if (
        agentRun?.transcript_groups &&
        Object.keys(agentRun.transcript_groups).length > 0
      ) {
        // Expand all groups by default
        const allGroupIds = Object.keys(agentRun.transcript_groups);
        setExpandedGroups(new Set(allGroupIds));
      }
    }, [agentRun?.transcript_groups]);

    // Build hierarchical transcript group structure
    const { transcriptGroupTree, ungroupedTranscripts, transcriptKeys } =
      useMemo(() => {
        if (!agentRun || Object.keys(agentRun.transcripts).length === 0) {
          return {
            transcriptGroupTree: [],
            ungroupedTranscripts: [],
            transcriptKeys: [],
          };
        }

        const transcriptGroups = agentRun.transcript_groups || {};
        const allTranscriptKeys: string[] = [];
        const groupToTranscripts: Record<string, string[]> = {};
        const groupToNode: Record<string, TranscriptGroupNode> = {};

        // First pass: collect all transcripts and their groups
        Object.entries(agentRun.transcripts).forEach(
          ([transcriptId, transcript]) => {
            allTranscriptKeys.push(transcriptId);

            if (
              transcript.transcript_group_id &&
              transcriptGroups[transcript.transcript_group_id]
            ) {
              const groupId = transcript.transcript_group_id;
              if (!groupToTranscripts[groupId]) {
                groupToTranscripts[groupId] = [];
              }
              groupToTranscripts[groupId].push(transcriptId);
            }
          }
        );

        // Second pass: build nodes for all groups
        Object.entries(transcriptGroups).forEach(([groupId, group]) => {
          groupToNode[groupId] = {
            group,
            transcripts: groupToTranscripts[groupId] || [],
            children: [],
            level: 0, // Will be calculated in the next pass
          };
        });

        // Third pass: build the tree structure and calculate levels
        const rootNodes: TranscriptGroupNode[] = [];
        const processedGroups = new Set<string>();

        const calculateLevel = (groupId: string, level: number): number => {
          if (processedGroups.has(groupId)) {
            return level;
          }

          processedGroups.add(groupId);
          const node = groupToNode[groupId];
          if (!node) return level;

          node.level = level;

          // Find children (groups that have this group as parent)
          const children = Object.values(transcriptGroups).filter(
            (g) => g.parent_transcript_group_id === groupId
          );

          node.children = children
            .map((child) => {
              const childNode = groupToNode[child.id];
              if (childNode) {
                calculateLevel(child.id, level + 1);
                return childNode;
              }
              return null;
            })
            .filter((n): n is TranscriptGroupNode => n !== null);

          return level;
        };

        // Find root groups (no parent) and build the tree
        Object.values(transcriptGroups).forEach((group) => {
          if (!group.parent_transcript_group_id) {
            const node = groupToNode[group.id];
            if (node) {
              calculateLevel(group.id, 0);
              rootNodes.push(node);
            }
          }
        });

        // Sort transcripts within each group by created_at timestamp
        const sortTranscripts = (node: TranscriptGroupNode) => {
          node.transcripts = sortTranscriptsByTimestamp(
            node.transcripts,
            agentRun.transcripts
          );

          // Recursively sort children
          node.children.forEach(sortTranscripts);
        };

        rootNodes.forEach(sortTranscripts);

        // Find ungrouped transcripts
        const ungroupedTranscripts = allTranscriptKeys.filter(
          (transcriptId) =>
            !agentRun.transcripts[transcriptId].transcript_group_id
        );

        // Sort ungrouped transcripts by created_at timestamp
        const sortedUngroupedTranscripts = sortTranscriptsByTimestamp(
          ungroupedTranscripts,
          agentRun.transcripts
        );

        console.log(
          'Final tree structure:',
          rootNodes.map((node) => ({
            id: node.group.id,
            name: node.group.name,
            level: node.level,
            transcriptCount: node.transcripts.length,
            childCount: node.children.length,
          }))
        );

        // If no transcript groups are available, treat all transcripts as ungrouped
        if (Object.keys(transcriptGroups).length === 0) {
          console.log(
            'No transcript groups available, treating all transcripts as ungrouped'
          );
          return {
            transcriptGroupTree: [],
            ungroupedTranscripts: allTranscriptKeys,
            transcriptKeys: allTranscriptKeys,
          };
        }

        return {
          transcriptGroupTree: rootNodes,
          ungroupedTranscripts: sortedUngroupedTranscripts,
          transcriptKeys: allTranscriptKeys,
        };
      }, [agentRun]);

    const [transcript, transcriptIdx] = useMemo(() => {
      if (!agentRun || transcriptKeys.length === 0) {
        return [null, 0];
      }

      // Determine target transcript ID based on selection, initial index, or default
      let targetId: string;

      if (
        selectedTranscriptKey &&
        transcriptKeys.includes(selectedTranscriptKey)
      ) {
        // Use currently selected transcript
        targetId = selectedTranscriptKey;
      } else if (
        initialTranscriptIdx !== undefined &&
        transcriptKeys[initialTranscriptIdx]
      ) {
        // Use initial transcript index if provided and valid
        targetId = transcriptKeys[initialTranscriptIdx];
      } else {
        // Default to first transcript
        targetId = transcriptKeys[0];
      }

      // Update selected transcript key if it was null or if we're using initial index
      if (
        !selectedTranscriptKey ||
        (initialTranscriptIdx !== undefined &&
          transcriptKeys[initialTranscriptIdx])
      ) {
        setSelectedTranscriptKey(targetId);
      }

      return [agentRun.transcripts[targetId], transcriptKeys.indexOf(targetId)];
    }, [agentRun, selectedTranscriptKey, transcriptKeys, initialTranscriptIdx]);

    // Initialize pretty print for messages with JSON content when transcript changes
    useEffect(() => {
      if (transcript && transcript.messages.length > 0) {
        const jsonMessageIndices = new Set<number>();

        transcript.messages.forEach((message, index) => {
          const content = getMessageContent(message.content);
          if (hasJsonContent(content)) {
            jsonMessageIndices.add(index);
          }
        });

        setPrettyPrintJsonMessages(jsonMessageIndices);
      }
    }, [transcript]);

    // Handler for toggling group expansion
    const handleGroupToggle = useCallback((groupId: string) => {
      setExpandedGroups((prev) => {
        const newSet = new Set(prev);
        if (newSet.has(groupId)) {
          newSet.delete(groupId);
        } else {
          newSet.add(groupId);
        }
        return newSet;
      });
    }, []);

    // Handler for expanding/collapsing all groups
    const handleToggleAllGroups = useCallback(() => {
      if (!agentRun?.transcript_groups) return;

      const allGroupIds = Object.keys(agentRun.transcript_groups);
      const allExpanded = allGroupIds.every((id) => expandedGroups.has(id));

      if (allExpanded) {
        // Collapse all groups
        setExpandedGroups(new Set());
      } else {
        // Expand all groups
        setExpandedGroups(new Set(allGroupIds));
      }
    }, [agentRun?.transcript_groups, expandedGroups]);

    // Check if all groups are expanded
    const allGroupsExpanded = useMemo(() => {
      if (!agentRun?.transcript_groups) return false;
      const allGroupIds = Object.keys(agentRun.transcript_groups);
      return (
        allGroupIds.length > 0 &&
        allGroupIds.every((id) => expandedGroups.has(id))
      );
    }, [agentRun?.transcript_groups, expandedGroups]);

    // Handler for transcript selection
    const handleTranscriptSelect = useCallback(
      (transcriptKey: string) => {
        setSelectedTranscriptKey(transcriptKey);
        // Clear any highlighted citations when switching transcripts
        dispatch(clearHighlightedCitation());
      },
      [dispatch]
    );

    /**
     * Scrolling
     */
    const [scrollNode, setScrollNode] = useState<HTMLDivElement | null>(null);
    const [currentBlockIndex, setCurrentBlockIndex] = useState<number | null>(
      null
    );

    const [highlightedBlock, setHighlightedBlock] = useState<string | null>(
      null
    );

    // Store scroll positions per transcript
    const [transcriptScrollPositions, setTranscriptScrollPositions] = useState<
      Record<string, number>
    >({});

    // Debounced scroll position for the current transcript
    const debouncedScrollPosition = useDebounce(
      selectedTranscriptKey
        ? transcriptScrollPositions[selectedTranscriptKey] || 0
        : 0,
      100
    );

    const scrollContainerRef = useCallback(
      (node: HTMLDivElement) => {
        if (!node) return;
        // Store the node reference
        setScrollNode(node);

        // Update scroll position on scroll
        const handleScroll = () => {
          // Save scroll position for current transcript
          if (selectedTranscriptKey) {
            setTranscriptScrollPositions((prev) => ({
              ...prev,
              [selectedTranscriptKey]: node.scrollTop,
            }));
          }
        };
        node.addEventListener('scroll', handleScroll);
        return () => {
          node.removeEventListener('scroll', handleScroll);
        };
      },
      [selectedTranscriptKey]
    );

    // Restore scroll position when transcript changes
    useEffect(() => {
      if (scrollNode && selectedTranscriptKey) {
        const savedPosition =
          transcriptScrollPositions[selectedTranscriptKey] || 0;
        scrollNode.scrollTop = savedPosition;
      }
    }, [selectedTranscriptKey]);

    // Compute the current block index based on scroll position
    useEffect(() => {
      // Skip if no transcript or no scroll node
      if (!transcript || !scrollNode) return;

      // Get all block elements
      const blockElements = Array.from(
        document.querySelectorAll(
          `[id*="r-${secondary ? 1 : 0}_t-${transcriptIdx}_b-"]`
        )
      );
      if (blockElements.length === 0) return;

      // Use the stored node reference directly
      const containerRect = scrollNode.getBoundingClientRect();
      const viewportTop = containerRect.top;
      const viewportHeight = containerRect.height;

      // Calculate visibility for each block
      const visibilityScores = blockElements.map((element) => {
        const rect = element.getBoundingClientRect();

        // Calculate how much of the element is visible in the viewport
        const top = Math.max(rect.top, viewportTop);
        const bottom = Math.min(rect.bottom, viewportTop + viewportHeight);
        const visibleHeight = Math.max(0, bottom - top);

        // Calculate visibility as a percentage of the element's height
        const visibilityScore = visibleHeight / rect.height;

        // Extract block index from the id
        const blockIdx = parseInt(
          element.id.replace('b-', '').split('_')[2],
          10
        );

        return { blockIndex: blockIdx, visibilityScore };
      });

      // Find the block with the highest visibility score
      const mostVisibleBlock = visibilityScores.reduce(
        (prev, current) =>
          current.visibilityScore > prev.visibilityScore ? current : prev,
        { blockIndex: -1, visibilityScore: 0 }
      );

      // Only update if we found a visible block
      if (
        mostVisibleBlock.blockIndex >= 0 &&
        mostVisibleBlock.visibilityScore > 0
      ) {
        setCurrentBlockIndex(mostVisibleBlock.blockIndex);
      }
    }, [debouncedScrollPosition, transcript, scrollNode]);

    /**
     * Scroll to block function - now with cross-scrolling support
     */
    const scrollToBlock = useCallback(
      (
        toBlockIdx: number,
        toTranscriptIdx: number = 0,
        toAgentRunIdx: number = 0,
        highlightDuration: number = 0
      ) => {
        // Determine which transcript should handle this scroll
        const currentAgentRunIdx = secondary ? 1 : 0;

        if (toAgentRunIdx !== currentAgentRunIdx && otherAgentRunRef?.current) {
          // Cross-scroll to the other agent run
          otherAgentRunRef.current.scrollToBlock(
            toBlockIdx,
            toTranscriptIdx,
            (toAgentRunIdx + 1) % 2,
            highlightDuration
          );
          return;
        }

        // Handle scrolling within this agent run
        // First, change the selected transcript if needed
        const targetTranscriptKey = transcriptKeys[toTranscriptIdx];
        const needsTranscriptChange =
          targetTranscriptKey && targetTranscriptKey !== selectedTranscriptKey;

        if (needsTranscriptChange) {
          setSelectedTranscriptKey(targetTranscriptKey);
        }

        const tryScrolling = (attempts = 0, maxAttempts = 3) => {
          const blockId = `r-${toAgentRunIdx}_t-${toTranscriptIdx}_b-${toBlockIdx}`;
          const blockElement = document.getElementById(blockId);
          if (blockElement && scrollNode) {
            const containerRect = scrollNode.getBoundingClientRect();
            const elementRect = blockElement.getBoundingClientRect();
            const relativeTop =
              elementRect.top - containerRect.top + scrollNode.scrollTop;

            scrollNode.scrollTo({
              top: relativeTop,
              behavior: 'auto',
            });

            // Update current block index
            setCurrentBlockIndex(toBlockIdx);

            // Add highlighting effect
            setHighlightedBlock(blockId);

            // Remove highlight after animation duration
            setTimeout(() => {
              setHighlightedBlock(null);
            }, highlightDuration);

            return true;
          }

          // If element not found and we haven't exceeded max attempts
          if (attempts < maxAttempts) {
            // Try again after a short delay
            setTimeout(() => tryScrolling(attempts + 1, maxAttempts), 50);
            return false;
          }

          console.warn(
            `Failed to scroll to block ${toBlockIdx} after ${maxAttempts} attempts`
          );
          return false;
        };

        // If we changed the transcript, wait a bit for the UI to update before scrolling
        if (needsTranscriptChange) {
          setTimeout(() => tryScrolling(), 100);
        } else {
          tryScrolling();
        }
      },
      [
        scrollNode,
        secondary,
        otherAgentRunRef,
        transcriptKeys,
        selectedTranscriptKey,
      ]
    );

    React.useImperativeHandle(
      ref,
      () => ({
        scrollToBlock,
      }),
      [scrollToBlock]
    );

    /**
     * Block navigation
     */

    const goToNextBlock = useCallback(() => {
      if (!transcript) return;

      const nextIndex =
        currentBlockIndex !== null
          ? Math.min(currentBlockIndex + 1, transcript.messages.length - 1)
          : 0;

      scrollToBlock(nextIndex, transcriptIdx, secondary ? 1 : 0);
    }, [currentBlockIndex, transcript, scrollToBlock, transcriptIdx]);
    const goToPrevBlock = useCallback(() => {
      if (!transcript) return;

      const prevIndex =
        currentBlockIndex !== null ? Math.max(currentBlockIndex - 1, 0) : 0;

      scrollToBlock(prevIndex, transcriptIdx, secondary ? 1 : 0);
    }, [currentBlockIndex, transcript, scrollToBlock, transcriptIdx]);

    return (
      <Card
        className="h-full basis-1/2 p-3 min-h-0 min-w-0 flex flex-col space-y-3"
        style={{ flexGrow: '2' }}
      >
        {/* Header area Content */}
        {agentRun && (
          <>
            <div className="flex flex-col gap-1">
              <div className="flex items-center space-x-1">
                <div className="font-semibold text-sm">Agent Run</div>
                <UuidPill uuid={agentRun?.id} />
                {agentRun && (
                  <MetadataDialog
                    metadata={agentRun.metadata}
                    title="Agent Run Metadata"
                  />
                )}
              </div>
              <div className="text-xs text-muted-foreground flex items-center overflow-hidden truncate">
                {Object.entries(agentRun.metadata).map(([key, value]) => (
                  <span key={key} className="mr-3">
                    <span className="font-medium text-muted-foreground">
                      {key}:
                    </span>{' '}
                    {formatMetadataValue(value)}
                  </span>
                ))}
                ...
              </div>
            </div>
            <ResizablePanelGroup
              direction="horizontal"
              className="flex flex-1 min-h-0 w-full overflow-hidden relative"
            >
              {/* Transcript Groups and Transcripts Sidebar */}
              {transcriptKeys.length >= 2 && (
                <>
                  <ResizablePanel
                    defaultSize={25}
                    minSize={20}
                    maxSize={50}
                    className="flex flex-col"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="text-xs font-medium text-primary">
                        Transcripts
                      </div>
                      {/* Expand/Collapse All Button - only show if there are transcript groups */}
                      {transcriptGroupTree.length > 0 && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              onClick={handleToggleAllGroups}
                              className="p-0.5 rounded text-muted-foreground hover:text-primary hover:bg-muted transition-colors"
                              aria-label={
                                allGroupsExpanded
                                  ? 'Collapse all groups'
                                  : 'Expand all groups'
                              }
                            >
                              {allGroupsExpanded ? (
                                <Minimize2 className="h-3 w-3" />
                              ) : (
                                <Maximize2 className="h-3 w-3" />
                              )}
                            </button>
                          </TooltipTrigger>
                          <TooltipContent side="bottom" align="end">
                            <p>
                              {allGroupsExpanded
                                ? 'Collapse all groups'
                                : 'Expand all groups'}
                            </p>
                          </TooltipContent>
                        </Tooltip>
                      )}
                    </div>
                    <div className="space-y-1 flex-1 overflow-y-auto min-h-0 pr-1">
                      {/* Hierarchical Transcript Groups */}
                      {transcriptGroupTree.map((node) => (
                        <TranscriptGroupNode
                          key={node.group.id}
                          node={node}
                          selectedTranscriptKey={selectedTranscriptKey}
                          selectedTranscriptGroupId={selectedTranscriptGroupId}
                          expandedGroups={expandedGroups}
                          onTranscriptSelect={handleTranscriptSelect}
                          onGroupToggle={handleGroupToggle}
                          agentRun={agentRun}
                        />
                      ))}

                      {/* Root Level Transcripts (ungrouped) */}
                      {ungroupedTranscripts.map((transcriptKey) => (
                        <div
                          key={transcriptKey}
                          className={cn(
                            'flex items-center w-full text-xs rounded border transition-colors shadow-sm',
                            selectedTranscriptKey === transcriptKey
                              ? 'bg-blue-bg border-blue-border text-primary shadow-md'
                              : 'bg-secondary border-border text-primary hover:bg-blue-bg/50 hover:border-blue-border/50'
                          )}
                        >
                          <button
                            onClick={() =>
                              handleTranscriptSelect(transcriptKey)
                            }
                            className="flex-1 text-left px-2 py-1.5 text-ellipsis whitespace-nowrap overflow-hidden font-medium"
                            title={transcriptKey}
                          >
                            {transcriptKey}
                          </button>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <div className="flex h-full items-center">
                                <MetadataDialog
                                  metadata={
                                    agentRun?.transcripts[transcriptKey]
                                      ?.metadata || {}
                                  }
                                  title={`Transcript Metadata - ${transcriptKey}`}
                                  trigger={
                                    <button
                                      className={cn(
                                        'p-0.5 mr-1 rounded transition-colors',
                                        selectedTranscriptKey === transcriptKey
                                          ? 'hover:bg-blue-bg text-primary'
                                          : 'hover:bg-accent text-muted-foreground'
                                      )}
                                    >
                                      <FileText className="h-3 w-3" />
                                    </button>
                                  }
                                />
                              </div>
                            </TooltipTrigger>
                            <TooltipContent side="left" align="center">
                              <p>View transcript metadata</p>
                            </TooltipContent>
                          </Tooltip>
                        </div>
                      ))}
                    </div>
                  </ResizablePanel>
                  <ResizableHandle withHandle={false} />
                </>
              )}

              {transcript && (
                <ResizablePanel defaultSize={75} className="flex flex-col">
                  {/* Transcript content */}
                  <div className="space-y-1 mb-2 px-1">
                    <div className="flex items-center justify-between">
                      {selectedTranscriptKey && (
                        <div className="flex items-center space-x-1">
                          <div className="font-semibold text-sm">
                            Transcript
                          </div>
                          <UuidPill uuid={selectedTranscriptKey} />
                          <MetadataDialog
                            metadata={
                              agentRun?.transcripts[selectedTranscriptKey]
                                ?.metadata || {}
                            }
                            title={`Transcript Metadata - ${selectedTranscriptKey}`}
                          />
                        </div>
                      )}
                    </div>
                    {selectedTranscriptKey &&
                      agentRun?.transcripts[selectedTranscriptKey]
                        ?.transcript_group_id && (
                        <TranscriptPath
                          path={buildTranscriptPath(
                            selectedTranscriptKey,
                            agentRun
                          )}
                        />
                      )}
                  </div>
                  <div
                    className="space-y-2 overflow-y-auto custom-scrollbar flex-1 pl-1"
                    ref={scrollContainerRef}
                  >
                    {transcript.messages.map((message, index) => {
                      const blockId = `r-${secondary ? 1 : 0}_t-${transcriptIdx}_b-${index}`;
                      return (
                        <MessageBox
                          key={index}
                          message={message}
                          index={index}
                          blockId={blockId}
                          isHighlighted={highlightedBlock === blockId}
                          citedRanges={allCitations.filter(
                            (c) =>
                              c.transcript_idx === transcriptIdx &&
                              c.block_idx === index
                          )}
                          prettyPrintJsonMessages={prettyPrintJsonMessages}
                          setPrettyPrintJsonMessages={
                            setPrettyPrintJsonMessages
                          }
                        />
                      );
                    })}
                  </div>

                  {/* Navigation buttons inside the ScrollArea (relative to parent container) */}
                  <div className="absolute bottom-3 right-6 flex flex-col gap-1">
                    <div className="bg-muted border border-border rounded-md shadow-sm flex flex-col">
                      <button
                        onClick={goToPrevBlock}
                        className="p-1.5 hover:bg-accent transition-colors rounded-t-md"
                        title="Previous block"
                      >
                        <ChevronUp className="h-4 w-4 text-muted-foreground" />
                      </button>
                      <div className="h-px bg-accent" />
                      <button
                        onClick={goToNextBlock}
                        className="p-1.5 hover:bg-accent transition-colors rounded-b-md"
                        title="Next block"
                      >
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                      </button>
                    </div>
                  </div>
                </ResizablePanel>
              )}
            </ResizablePanelGroup>
          </>
        )}
        {!agentRun && (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        )}
      </Card>
    );
  }
);

// Add display name for forwardRef
AgentRunViewer.displayName = 'AgentRunViewer';

export default AgentRunViewer;

const MessageBox: React.FC<{
  message: ChatMessage;
  index: number;
  blockId?: string;
  isHighlighted: boolean;
  citedRanges: Citation[];
  prettyPrintJsonMessages: Set<number>;
  setPrettyPrintJsonMessages: React.Dispatch<React.SetStateAction<Set<number>>>;
}> = ({
  message,
  index,
  blockId: id,
  isHighlighted,
  citedRanges,
  prettyPrintJsonMessages,
  setPrettyPrintJsonMessages,
}) => {
  const dispatch = useAppDispatch();

  const highlightedCitationId = useAppSelector(
    (state) => state.transcript.highlightedCitationId
  );

  // Scroll to highlighted citation span
  useEffect(() => {
    if (highlightedCitationId) {
      // Use setTimeout to ensure highlighting has been applied to DOM
      setTimeout(() => {
        const targetSpan = document.querySelector(
          `span[data-citation-ids*="${highlightedCitationId}"]`
        );
        if (targetSpan) {
          targetSpan.scrollIntoView({
            behavior: 'instant',
            block: 'center',
            inline: 'nearest',
          });
        }
      }, 50);
    }
  }, [highlightedCitationId]);

  // Helper function to extract text content from message content
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
    const originalToPrety: number[] = new Array(originalText.length);
    const prettyToOriginal: number[] = new Array(prettyText.length);

    let originalPos = 0;
    let prettyPos = 0;

    while (originalPos < originalText.length && prettyPos < prettyText.length) {
      const originalChar = originalText[originalPos];
      const prettyChar = prettyText[prettyPos];

      if (originalChar === prettyChar) {
        // Exact match - record the mapping
        originalToPrety[originalPos] = prettyPos;
        prettyToOriginal[prettyPos] = originalPos;
        originalPos++;
        prettyPos++;
      } else if (/\s/.test(originalChar) && /\s/.test(prettyChar)) {
        // Both are whitespace - advance both but prefer the pretty position mapping
        originalToPrety[originalPos] = prettyPos;
        prettyToOriginal[prettyPos] = originalPos;
        originalPos++;
        prettyPos++;
      } else if (/\s/.test(prettyChar)) {
        // Pretty has extra whitespace (common in formatted JSON)
        prettyToOriginal[prettyPos] = originalPos;
        prettyPos++;
      } else if (/\s/.test(originalChar)) {
        // Original has whitespace that was removed/changed
        originalToPrety[originalPos] = prettyPos;
        originalPos++;
      } else {
        // Non-matching characters - this shouldn't happen with valid JSON formatting
        originalToPrety[originalPos] = prettyPos;
        prettyToOriginal[prettyPos] = originalPos;
        originalPos++;
        prettyPos++;
      }
    }

    // Fill in any remaining positions
    while (originalPos < originalText.length) {
      originalToPrety[originalPos] = prettyText.length;
      originalPos++;
    }
    while (prettyPos < prettyText.length) {
      prettyToOriginal[prettyPos] = originalText.length;
      prettyPos++;
    }

    return { originalToPrety, prettyToOriginal };
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
    const messageContent = getMessageContent(message.content);
    return computeCitationIntervals(messageContent, citedRanges);
  }, [message.content, citedRanges]);

  // Memoize matched citation IDs for dispatch
  const matchedCitationIds = useMemo(() => {
    const ids = new Set<string>();
    allCitationIntervals.forEach(({ start, end, id }) => {
      if (start < end) {
        ids.add(id);
      }
    });
    return Array.from(ids);
  }, [allCitationIntervals]);

  // Dispatch matched citations after render to avoid state updates during render
  useEffect(() => {
    if (matchedCitationIds.length > 0) {
      dispatch(addMatchedCitations(matchedCitationIds));
    }
  }, [dispatch, matchedCitationIds]);

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
    const matchedIds = new Set<string>();
    citationIntervals.forEach(({ start, end, id }) => {
      if (start >= end) return;
      if (!opens[start]) opens[start] = [];
      if (!closes[end]) closes[end] = [];
      opens[start].push(id);
      closes[end].push(id);
      matchedIds.add(id);
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

  // Helper to render tool calls for assistant messages
  const renderToolCalls = () => {
    if (message.role === 'assistant' && message.tool_calls) {
      return message.tool_calls.map((tool, i) => (
        <div
          key={i}
          className="mt-1 p-1.5 bg-secondary/85 rounded text-xs break-all whitespace-pre-wrap"
        >
          <div className="text-[10px] text-muted-foreground mb-0.5">
            Tool Call ID: {tool.id}
          </div>
          {tool.view ? (
            <span className="font-mono">{tool.view.content}</span>
          ) : (
            <div className="font-mono">
              <span className="font-semibold">{tool.function}</span>
              <span className="text-muted-foreground">
                (
                {Object.entries(tool.arguments || {})
                  .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
                  .join(', ')}
                )
              </span>
            </div>
          )}
        </div>
      ));
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
                <div className="mb-2 px-2 py-2 bg-muted border-l-2 border-border text-xs text-primary italic whitespace-pre-wrap [overflow-wrap:anywhere] max-w-full overflow-x-auto font-mono rounded">
                  {getReasoningContent(message.content)}
                </div>
              )}
          </>
        )}
        <div className="whitespace-pre-wrap [overflow-wrap:anywhere] max-w-full text-xs overflow-x-auto font-mono">
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
};
