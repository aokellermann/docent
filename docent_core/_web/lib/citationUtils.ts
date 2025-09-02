import { Citation } from '../app/types/experimentViewerTypes';
import { useAppDispatch } from '../app/store/hooks';
import {
  setHighlightedCitation,
  clearHighlightedCitation,
} from '../app/store/transcriptSlice';
import { RootState } from '../app/store/store';

/**
 * Generate a unique, consistent ID for a citation
 */
export const generateCitationId = (citation: Citation): string => {
  return `${citation.transcript_idx}-${citation.block_idx}-${citation.start_idx}-${citation.end_idx}`;
};

/**
 * Check if two citations are the same
 */
export const citationsEqual = (a: Citation, b: Citation): boolean => {
  return (
    a.transcript_idx === b.transcript_idx &&
    a.block_idx === b.block_idx &&
    a.start_idx === b.start_idx &&
    a.end_idx === b.end_idx
  );
};

/**
 * Selector to check if a citation is highlighted
 */
export const selectIsCitationHighlighted = (
  state: RootState,
  citation: Citation
): boolean => {
  const citationId = generateCitationId(citation);
  return state.transcript.highlightedCitationId === citationId;
};

/**
 * Hook for citation highlighting functionality
 */
export const useCitationHighlight = () => {
  const dispatch = useAppDispatch();

  const highlightCitation = (citation: Citation) => {
    const citationId = generateCitationId(citation);
    dispatch(setHighlightedCitation(citationId));
  };

  const clearHighlight = () => {
    dispatch(clearHighlightedCitation());
  };

  return {
    highlightCitation,
    clearHighlight,
  };
};
