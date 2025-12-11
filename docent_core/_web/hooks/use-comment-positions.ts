import { useLayoutEffect, useEffect, useState, useRef } from 'react';
import { Comment } from '@/app/api/labelApi';

const CARD_HEIGHT = 150;
const FOCUSED_CARD_HEIGHT = 250;
const OVERLAP_THRESHOLD = 80;

function getCardHeight(comment: Comment, isFocused: boolean): number {
  if (comment.id === 'draft') return FOCUSED_CARD_HEIGHT;
  if (isFocused) return FOCUSED_CARD_HEIGHT;
  return CARD_HEIGHT;
}

function getIdealY(
  comment: Comment,
  scrollContainer: HTMLElement
): number | null {
  // Try highlight element first, then fall back to block element
  let targetElement = document.querySelector(
    `[data-comment-id="${comment.id}"]`
  ) as HTMLElement;

  const firstTarget = comment.citations?.[0]?.target;
  if (!targetElement && firstTarget?.item.item_type === 'block_content') {
    const blockIdx = firstTarget.item.block_idx;
    targetElement = document.querySelector(
      `[id$="_b-${blockIdx}"]`
    ) as HTMLElement;
  }

  if (!targetElement) return null;

  const targetRect = targetElement.getBoundingClientRect();
  const containerRect = scrollContainer.getBoundingClientRect();
  const relativeTop =
    targetRect.top - containerRect.top + scrollContainer.scrollTop;

  // Block-level: align top; Text selections: center on highlight
  if (!firstTarget?.text_range) {
    return relativeTop;
  }
  return Math.max(0, relativeTop - CARD_HEIGHT / 2);
}

/** Create a stable key that includes comment citations, not just IDs */
function getCommentsKey(comments: Comment[]): string {
  return comments
    .map((c) => {
      const target = c.citations?.[0]?.target;
      if (!target) return c.id;
      const item = target.item;
      const blockIdx = item.item_type === 'block_content' ? item.block_idx : '';
      const startIdx = target.text_range?.target_start_idx ?? '';
      return `${c.id}:${blockIdx}:${startIdx}`;
    })
    .join(',');
}

function computePositions(
  comments: Comment[],
  scrollContainer: HTMLElement,
  focusedCommentId: string | null
): Map<string, number> {
  if (comments.length === 0) return new Map();

  const focusedIdx = focusedCommentId
    ? comments.findIndex((c) => c.id === focusedCommentId)
    : -1;

  const positions = new Map<string, number>();

  // If focused, start from focused comment; otherwise start from first
  const startIdx = focusedIdx >= 0 ? focusedIdx : 0;
  const startComment = comments[startIdx];
  const startIdealY = getIdealY(startComment, scrollContainer);

  if (startIdealY === null) return positions;

  // Place the starting comment
  positions.set(startComment.id, startIdealY);

  // Stack downward from start
  let currentY =
    startIdealY + getCardHeight(startComment, focusedIdx === startIdx);
  for (let i = startIdx + 1; i < comments.length; i++) {
    const comment = comments[i];
    const idealY = getIdealY(comment, scrollContainer);
    if (idealY === null) continue;

    const cardHeight = getCardHeight(comment, false);
    if (currentY > idealY - OVERLAP_THRESHOLD) {
      positions.set(comment.id, currentY);
      currentY += cardHeight;
    } else {
      positions.set(comment.id, idealY);
      currentY = idealY + cardHeight;
    }
  }

  // Stack upward from start (only if we started from a focused comment)
  if (startIdx > 0) {
    currentY = startIdealY - CARD_HEIGHT;
    for (let i = startIdx - 1; i >= 0; i--) {
      const comment = comments[i];
      const idealY = getIdealY(comment, scrollContainer);
      if (idealY === null) continue;

      const cardHeight = getCardHeight(comment, false);
      if (currentY < idealY + OVERLAP_THRESHOLD) {
        positions.set(comment.id, currentY);
        currentY -= cardHeight;
      } else {
        positions.set(comment.id, idealY);
        currentY = idealY - cardHeight;
      }
    }
  }

  return positions;
}

interface UseCommentPositionsParams {
  sortedComments: Comment[];
  scrollContainer: HTMLElement | null;
  focusedCommentId: string | null;
  enabled: boolean;
}

export function useCommentPositions({
  sortedComments,
  scrollContainer,
  focusedCommentId,
  enabled,
}: UseCommentPositionsParams): Map<string, number> {
  const [positions, setPositions] = useState<Map<string, number>>(new Map());

  // Track previous focused ID to detect deselection (someId → null)
  const prevFocusedIdRef = useRef<string | null>(focusedCommentId);
  // Track the anchor used for the last position calculation (for resize)
  const lastAnchorRef = useRef<string | null>(focusedCommentId);

  // Create a key that changes when comment locations change (not just IDs)
  const commentsKey = getCommentsKey(sortedComments);

  // Calculate positions after DOM updates using useLayoutEffect
  // This runs synchronously after all DOM mutations but before paint,
  // ensuring highlight elements from sibling components exist
  useLayoutEffect(() => {
    if (!enabled || !scrollContainer) {
      setPositions((prev) => (prev.size === 0 ? prev : new Map()));
      prevFocusedIdRef.current = focusedCommentId;
      return;
    }

    // Skip recalculation when deselecting (going from someId → null)
    // This keeps positions stable when clicking away
    const isDeselecting =
      prevFocusedIdRef.current !== null && focusedCommentId === null;
    prevFocusedIdRef.current = focusedCommentId;

    if (isDeselecting) {
      return;
    }

    // Use the new focused ID as anchor, or keep the last anchor if deselected
    const anchor = focusedCommentId ?? lastAnchorRef.current;
    lastAnchorRef.current = anchor;

    const newPositions = computePositions(
      sortedComments,
      scrollContainer,
      anchor
    );

    // Only update if positions actually changed to avoid infinite loops
    setPositions((prev) => {
      if (prev.size !== newPositions.size) return newPositions;
      let hasChanged = false;
      newPositions.forEach((value, key) => {
        if (prev.get(key) !== value) hasChanged = true;
      });
      return hasChanged ? newPositions : prev;
    });
    // sortedComments content is tracked via commentsKey
    // scrollContainer is a direct dependency - when it transitions from null to valid, effect re-runs
  }, [commentsKey, focusedCommentId, enabled, scrollContainer]);

  // Listen for window resize
  useEffect(() => {
    if (!enabled || !scrollContainer) return;
    const handleResize = () => {
      // Use lastAnchorRef to maintain the same anchor after deselection
      const newPositions = computePositions(
        sortedComments,
        scrollContainer,
        lastAnchorRef.current
      );
      setPositions(newPositions);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, commentsKey, scrollContainer]);

  return positions;
}
