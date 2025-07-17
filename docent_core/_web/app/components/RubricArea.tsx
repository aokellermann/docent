'use client';

import { useMemo, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';

import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Textarea } from '@/components/ui/textarea';

import { useAppDispatch, useAppSelector } from '../store/hooks';

import {
  setActiveRubricId,
  clearJudgeResults,
  setEditingRubricId,
  clearCentroids,
} from '../store/rubricSlice';

import { ProgressBar } from './ProgressBar';
import RubricEditor from '../dashboard/[collection_id]/components/RubricEditor';
import RubricList from '../dashboard/[collection_id]/components/RubricList';
import { JudgeResultsList } from '../dashboard/[collection_id]/components/JudgeResultsSection';
import {
  useCancelEvaluationMutation,
  useUpdateRubricMutation,
  useListenForJudgeResultsQuery,
  useStartEvaluationMutation,
  useProposeCentroidsMutation,
  useStartCentroidAssignmentMutation,
  useListenForCentroidAssignmentsQuery,
  useCancelAssignmentMutation,
} from '../api/rubricApi';
import { toast } from '@/hooks/use-toast';

const RubricArea = () => {
  const dispatch = useAppDispatch();
  const searchParams = useSearchParams();
  const [shouldListenForResults, setShouldListenForResults] = useState(false);
  const [shouldListenForAssignments, setShouldListenForAssignments] =
    useState(false);
  const [isReclusterPopoverOpen, setIsReclusterPopoverOpen] = useState(false);
  const [feedbackText, setFeedbackText] = useState('');

  const [cancelEvaluation, { isLoading: isCancellingEvaluation }] =
    useCancelEvaluationMutation();
  const [updateRubric, { isLoading: isUpdatingRubric }] =
    useUpdateRubricMutation();

  const collectionId = useAppSelector((state) => state.collection.collectionId);
  const isPollingResults = useAppSelector(
    (state) => state.rubric.isPollingResults
  );
  const activeRubricJobId = useAppSelector(
    (state) => state.rubric.activeRubricJobId
  );
  const totalAgentRuns = useAppSelector((state) => state.rubric.totalAgentRuns);
  const judgeResultsMap = useAppSelector(
    (state) => state.rubric.judgeResultsMap
  );

  // Collect rubrics
  const rubricsMap = useAppSelector((state) => state.rubric.rubricsMap);
  const activeRubricId = useAppSelector((state) => state.rubric.activeRubricId);
  const editingRubricId = useAppSelector(
    (state) => state.rubric.editingRubricId
  );
  const activeRubric = useMemo(() => {
    if (!activeRubricId) return null;
    return rubricsMap[activeRubricId];
  }, [activeRubricId, rubricsMap]);
  const editingRubric = useMemo(() => {
    if (!editingRubricId) return null;
    return rubricsMap[editingRubricId];
  }, [editingRubricId, rubricsMap]);

  // Handle starting evaluations
  const [startEvaluation] = useStartEvaluationMutation();
  const handleEvaluate = async (rubricId: string, activateUi = true) => {
    if (!collectionId) return;

    // First start the job
    await startEvaluation({
      collectionId,
      rubricId,
    });
    if (activateUi) {
      // We set the active rubric *after* starting the job; this helps avoid a race condition
      // where we start listening before the job even exists, and thus it immediately closes.
      dispatch(setActiveRubricId(rubricId));
      setShouldListenForResults(true);
    }
  };

  // Handle URL-based rubric activation
  const alreadyInitiated = useRef(false);
  useEffect(() => {
    const urlRubricId = searchParams.get('activeRubricId');
    if (
      urlRubricId &&
      rubricsMap &&
      rubricsMap[urlRubricId] &&
      activeRubricId === null
    ) {
      if (alreadyInitiated.current) return;
      alreadyInitiated.current = true;

      // Active interface and listen for results without triggering a new job
      dispatch(setActiveRubricId(urlRubricId));
      setShouldListenForResults(true);
    }
  }, [searchParams, rubricsMap, activeRubricId, dispatch]);

  // If there is an active rubric job, listen for judge results with RTK
  useListenForJudgeResultsQuery(
    {
      collectionId: collectionId!,
      rubricId: activeRubric?.id || '',
    },
    {
      skip: !collectionId || !activeRubric || !shouldListenForResults,
    }
  );

  const handleCancelRubricJob = async () => {
    if (!collectionId || !activeRubricJobId || !activeRubricId) return;
    await cancelEvaluation({
      collectionId,
      rubricId: activeRubricId,
      jobId: activeRubricJobId,
    });

    // Kill the listening job
    setShouldListenForResults(false);
    setShouldListenForAssignments(false);
  };

  const resetInterface = () => {
    dispatch(setActiveRubricId(null));
    dispatch(clearJudgeResults());
    dispatch(clearCentroids());
    setShouldListenForResults(false);
    setShouldListenForAssignments(false);
  };

  const handleSaveRubric = async (rubric: any) => {
    if (!collectionId) return;

    try {
      await updateRubric({
        collectionId,
        rubricId: rubric.id,
        rubric,
      }).unwrap();

      // Clear editing state after successful update
      dispatch(setEditingRubricId(null));
    } catch (error) {
      console.error('Failed to update rubric:', error);
      toast({
        title: 'Error',
        description: 'Failed to update rubric',
        variant: 'destructive',
      });
    }
  };

  const handleShare = async () => {
    if (!activeRubricId) return;

    try {
      const currentUrl = new URL(window.location.href);
      currentUrl.searchParams.set('activeRubricId', activeRubricId);

      await navigator.clipboard.writeText(currentUrl.toString());

      toast({
        title: 'Link copied',
        description: 'Rubric link copied to clipboard',
      });
    } catch (error) {
      console.error('Failed to copy link:', error);
      toast({
        title: 'Error',
        description: 'Failed to copy link to clipboard',
        variant: 'destructive',
      });
    }
  };

  /**
   * Clustering
   */
  const centroidsMap = useAppSelector((state) => state.rubric.centroidsMap);
  const activeCentroidAssignmentJobId = useAppSelector(
    (state) => state.rubric.activeCentroidAssignmentJobId
  );
  const [proposeCentroids, { isLoading: isProposingCentroids }] =
    useProposeCentroidsMutation();
  const [startCentroidAssignment] = useStartCentroidAssignmentMutation();

  const handleProposeCentroids = async (feedback?: string) => {
    if (!collectionId || !activeRubricId) return;

    await proposeCentroids({
      collectionId,
      rubricId: activeRubricId,
      feedback,
    });

    // After proposing centroids, trigger centroid assignment
    await startCentroidAssignment({
      collectionId,
      rubricId: activeRubricId,
    });
    setShouldListenForAssignments(true);
  };

  const handleReclusterSubmit = async () => {
    await handleProposeCentroids(feedbackText.trim() || undefined);
    setIsReclusterPopoverOpen(false);
    setFeedbackText('');
  };

  const handleReclusterCancel = () => {
    setIsReclusterPopoverOpen(false);
    setFeedbackText('');
  };

  const [cancelAssignment, { isLoading: isCancellingAssignment }] =
    useCancelAssignmentMutation();
  const handleCancelAssignmentJob = async () => {
    if (!collectionId || !activeCentroidAssignmentJobId || !activeRubricId)
      return;
    await cancelAssignment({
      collectionId,
      rubricId: activeRubricId,
      jobId: activeCentroidAssignmentJobId,
    });

    // Kill the listening job
    setShouldListenForAssignments(false);
  };

  // If there are centroids, listen for assignments
  useListenForCentroidAssignmentsQuery(
    {
      collectionId: collectionId!,
      rubricId: activeRubricId!,
    },
    {
      skip: !collectionId || !activeRubricId || !shouldListenForAssignments,
    }
  );

  const reclusterPopover = (
    <Popover
      open={isReclusterPopoverOpen}
      onOpenChange={setIsReclusterPopoverOpen}
    >
      <PopoverTrigger asChild>
        <Button
          type="button"
          size="sm"
          className="gap-1 h-7 text-xs"
          variant="outline"
          disabled={isProposingCentroids}
        >
          {isProposingCentroids ? 'Proposing...' : 'Re-cluster results'}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-96 p-2 space-y-2">
        <div className="space-y-2">
          <div className="text-sm">
            Provide feedback for re-clustering (optional)
          </div>
          <Textarea
            id="feedback"
            placeholder="Describe how you'd like clusters to be improved..."
            value={feedbackText}
            onChange={(e) => setFeedbackText(e.target.value)}
            className="min-h-[80px] resize-none text-xs"
          />
        </div>
        <div className="flex items-center justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="text-xs"
            onClick={handleReclusterCancel}
          >
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            className="text-xs"
            onClick={handleReclusterSubmit}
            disabled={isProposingCentroids}
          >
            {isProposingCentroids ? 'Proposing...' : 'Re-cluster'}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );

  return (
    <Card className="h-full flex overflow-y-auto flex-col flex-1 p-3 custom-scrollbar space-y-3">
      {/* Rubric Display */}
      <div className="space-y-2">
        <div className="flex flex-col">
          <div className="text-sm font-semibold">Rubric Evaluation</div>
          <div className="text-xs text-muted-foreground">
            Define evaluation criteria and rules for agent performance
          </div>
        </div>

        {/* Rubric List - show when not actively evaluating */}
        {!activeRubric && <RubricList handleEvaluate={handleEvaluate} />}

        {/* Display the active rubric but with read only */}
        {activeRubric && (
          <RubricEditor
            initRubric={activeRubric}
            onSave={() => {}}
            onCloseWithoutSave={() => {}}
            readOnly={true}
          />
        )}
        {/* Editor */}
        {editingRubric && (
          <RubricEditor
            initRubric={editingRubric}
            onSave={handleSaveRubric}
            onCloseWithoutSave={() => dispatch(setEditingRubricId(null))}
            readOnly={isPollingResults || isUpdatingRubric}
          />
        )}

        {/* Progress bar */}
        {activeRubric && isPollingResults && (
          <ProgressBar
            current={Object.keys(judgeResultsMap ?? {}).length}
            total={totalAgentRuns}
            paused={false}
          />
        )}

        {/* Action Buttons */}
        {activeRubric && (
          <div className="flex items-center justify-end gap-2 pt-1">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="gap-1 h-7 text-xs"
              onClick={handleShare}
            >
              Share
            </Button>
            {!isPollingResults && (
              <>
                {Object.keys(centroidsMap).length === 0 && (
                  <Button
                    type="button"
                    size="sm"
                    className="gap-1 h-7 text-xs"
                    variant="outline"
                    disabled={isProposingCentroids}
                    onClick={() => handleProposeCentroids()}
                  >
                    {isProposingCentroids ? 'Proposing...' : 'Cluster results'}
                  </Button>
                )}
                {!activeCentroidAssignmentJobId &&
                  Object.keys(centroidsMap).length > 0 &&
                  reclusterPopover}
                {activeCentroidAssignmentJobId && (
                  <Button
                    type="button"
                    size="sm"
                    className="gap-1 h-7 text-xs"
                    disabled={isCancellingAssignment}
                    variant="outline"
                    onClick={() => handleCancelAssignmentJob()}
                  >
                    {isCancellingAssignment
                      ? 'Stopping...'
                      : 'Stop centroid assignment'}
                  </Button>
                )}
                <Button
                  type="button"
                  size="sm"
                  className="gap-1 h-7 text-xs"
                  onClick={() => resetInterface()}
                >
                  Exit
                </Button>
              </>
            )}
            {isPollingResults && (
              <>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="gap-1 h-7 text-xs"
                  onClick={() => resetInterface()}
                >
                  Run in background
                </Button>
                <Button
                  type="button"
                  size="sm"
                  className="gap-1 h-7 text-xs"
                  disabled={isCancellingEvaluation || !activeRubricJobId}
                  onClick={() => handleCancelRubricJob()}
                >
                  {isCancellingEvaluation ? 'Stopping...' : 'Stop'}
                </Button>
              </>
            )}
          </div>
        )}

        {/* Results */}
        {activeRubric && <JudgeResultsList />}
      </div>
    </Card>
  );
};

export default RubricArea;
