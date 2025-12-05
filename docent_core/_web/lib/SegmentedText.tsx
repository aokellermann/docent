import React from 'react';
import {
  computeSegmentsFromIntervals,
  TextSpanWithCitations,
} from '@/lib/citationMatch';
import { cn } from '@/lib/utils';
import { useAppSelector } from '@/app/store/hooks';
import {
  setSelectedAnnotationId,
  setAnnotationSidebarCollapsed,
} from '@/app/store/transcriptSlice';
import { useAppDispatch } from '@/app/store/hooks';

const getCitationColors = (
  role: string | undefined,
  isHighlighted: boolean
) => {
  if (!role) {
    return 'bg-yellow-300 dark:bg-yellow-700 text-black dark:text-white';
  }
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

const getAnnotationColors = (
  isHighlighted: boolean,
  isHovered: boolean,
  isSelected: boolean
) => {
  // Annotations use purple color scheme to distinguish from regular citations
  if (isHighlighted) {
    return 'bg-purple-600 text-white';
  }
  if (isHovered) {
    return 'bg-purple-400/40 border-b-2 border-purple-500/50';
  }
  if (isSelected) {
    return 'bg-purple-400/40 border-b-2 border-purple-500/50';
  }
  return 'bg-purple-500/20';
};

export interface SegmentedTextProps {
  text: string;
  intervals: TextSpanWithCitations[];
  role?: string;
  highlightedCitationId?: string | null;
  className?: string;
}

export const SegmentedText: React.FC<SegmentedTextProps> = ({
  text,
  intervals,
  role = undefined,
  highlightedCitationId = null,
  className,
}) => {
  const dispatch = useAppDispatch();

  const hoveredAnnotationId = useAppSelector(
    (state) => state.transcript.hoveredAnnotationId
  );

  const selectedAnnotationId = useAppSelector(
    (state) => state.transcript.selectedAnnotationId
  );

  const handleAnnotationClick = (annotationId: string) => {
    dispatch(setSelectedAnnotationId(annotationId));
    dispatch(setAnnotationSidebarCollapsed(false));
  };

  const segments = computeSegmentsFromIntervals(text, intervals);

  return (
    <span className={className}>
      {segments.map((seg, i) => {
        if (!seg.citationIds.length)
          return <React.Fragment key={`seg-${i}`}>{seg.text}</React.Fragment>;

        // Check if this segment contains an annotation
        const annotationInfo = intervals.find(
          (iv) =>
            iv.annotationId !== undefined &&
            seg.citationIds.includes(iv.citationId)
        );
        const isAnnotation = !!annotationInfo;

        const isHighlighted = highlightedCitationId
          ? seg.citationIds.includes(highlightedCitationId)
          : false;

        const isHovered = hoveredAnnotationId
          ? annotationInfo?.annotationId === hoveredAnnotationId
          : false;

        const isSelected = selectedAnnotationId
          ? annotationInfo?.annotationId === selectedAnnotationId
          : false;

        // Use role-based colors if role is provided and highlightedCitationId exists,
        // otherwise use simple yellow highlighting for metadata
        // Use annotation colors if this is an annotation, otherwise regular citation colors
        const colorClass = isAnnotation
          ? getAnnotationColors(isHighlighted, isHovered, isSelected)
          : getCitationColors(role, isHighlighted);

        return (
          <span
            key={`seg-${i}`}
            className={cn(
              colorClass,
              isAnnotation && 'cursor-pointer transition-all duration-150',
              isAnnotation && 'hover:border-purple-500/50 hover:border-b-2'
            )}
            data-citation-ids={seg.citationIds.join(',')}
            data-annotation-id={annotationInfo?.annotationId}
            onClick={
              isAnnotation && annotationInfo?.annotationId
                ? () => handleAnnotationClick(annotationInfo.annotationId!)
                : undefined
            }
          >
            {seg.text}
          </span>
        );
      })}
    </span>
  );
};
