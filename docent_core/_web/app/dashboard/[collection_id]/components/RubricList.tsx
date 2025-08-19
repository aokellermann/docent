'use client';

import { Plus, Play, FileText, Trash2, Pause } from 'lucide-react';
import { useAppDispatch, useAppSelector } from '@/app/store/hooks';
import { type Rubric } from '@/app/store/rubricSlice';
import { Button } from '@/components/ui/button';
import { useRouter } from 'next/navigation';
import { useCreateOrGetSessionMutation } from '@/app/api/refinementApi';
import {
  useGetRubricsQuery,
  useCreateRubricMutation,
  useDeleteRubricMutation,
  useStartEvaluationMutation,
  useGetRubricJobStatusQuery,
  useCancelEvaluationMutation,
} from '@/app/api/rubricApi';
import { toast } from '@/hooks/use-toast';
import { useHasCollectionWritePermission } from '@/lib/permissions/hooks';

interface RubricCardProps {
  rubric: Rubric;
  collectionId: string;
  hasWritePermission: boolean;
}

function RubricCard({
  rubric,
  collectionId,
  hasWritePermission,
}: RubricCardProps) {
  const dispatch = useAppDispatch();
  const router = useRouter();
  const [createOrGetSession, { isLoading: isCreatingSession }] =
    useCreateOrGetSessionMutation();

  // Get job status for this rubric
  const { data: jobDetails } = useGetRubricJobStatusQuery({
    collectionId,
    rubricId: rubric.id,
  });

  // Each card has its own cancellation mutation
  const [cancelEvaluation, { isLoading: isCancellingJob }] =
    useCancelEvaluationMutation();
  const handleCancelJob = async (jobId: string) => {
    try {
      await cancelEvaluation({
        collectionId,
        rubricId: rubric.id,
        jobId,
      }).unwrap();
    } catch (error) {
      console.error('Failed to cancel job:', error);
      toast({
        title: 'Error',
        description: 'Failed to cancel job',
        variant: 'destructive',
      });
    }
  };

  const [deleteRubric, { isLoading: isDeletingRubric }] =
    useDeleteRubricMutation();
  const handleDelete = async (rubricId: string) => {
    if (!collectionId) return;

    try {
      await deleteRubric({
        collectionId,
        rubricId,
      }).unwrap();
    } catch (error) {
      console.error('Failed to delete rubric:', error);
      toast({
        title: 'Error',
        description: 'Failed to delete rubric',
        variant: 'destructive',
      });
    }
  };

  const getRubricPreview = (rubric: Rubric) => {
    const description = rubric.high_level_description || 'No description';
    const inclusionCount = rubric.inclusion_rules.length;
    const exclusionCount = rubric.exclusion_rules.length;

    return {
      description:
        description.length > 100
          ? description.substring(0, 100) + '...'
          : description,
      inclusionCount,
      exclusionCount,
    };
  };

  const preview = getRubricPreview(rubric);
  const hasActiveJob =
    jobDetails?.status === 'pending' || jobDetails?.status === 'running';

  const handleClickRefine = async () => {
    if (!collectionId) return;
    try {
      const res = await createOrGetSession({
        collectionId,
        rubricId: rubric.id,
      }).unwrap();
      console.log('res', res);
      router.push(`/dashboard/${collectionId}/refine/${res.id}`);
    } catch (error) {
      console.error('Failed to start refinement session:', error);
      toast({
        title: 'Error',
        description: 'Failed to start refinement session',
        variant: 'destructive',
      });
    }
  };

  const handleClick = () => {
    router.push(`/dashboard/${collectionId}?rubricId=${rubric.id}`);
  };

  const [startEvaluation] = useStartEvaluationMutation();

  return (
    <div
      key={rubric.id}
      className="group relative border rounded-md transition-all duration-200 cursor-pointer border-border bg-secondary/50 hover:bg-secondary hover:shadow-sm"
      onClick={handleClick}
    >
      <div className={`p-2.5 ${hasWritePermission ? 'pr-28' : 'pr-12'}`}>
        {/* Icon and Description */}
        <div className="flex items-start gap-2">
          <FileText className="h-3.5 w-3.5 text-muted-foreground mt-0.5 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-xs font-mono text-primary line-clamp-2">
              {preview.description}
            </p>

            {/* Rule counts */}
            <div className="flex items-center gap-3 mt-1">
              {preview.inclusionCount > 0 && (
                <div className="flex items-center gap-1">
                  <div className="w-1.5 h-1.5 rounded-full bg-green-text"></div>
                  <span className="text-[10px] text-green-text">
                    {preview.inclusionCount} inclusion
                  </span>
                </div>
              )}
              {preview.exclusionCount > 0 && (
                <div className="flex items-center gap-1">
                  <div className="w-1.5 h-1.5 rounded-full bg-red-text"></div>
                  <span className="text-[10px] text-red-text">
                    {preview.exclusionCount} exclusion
                  </span>
                </div>
              )}
              {preview.inclusionCount === 0 && preview.exclusionCount === 0 && (
                <span className="text-[10px] text-muted-foreground">
                  No rules defined
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Action buttons */}
      <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
        {/* {hasWritePermission && (
          <button
            className={`p-1.5 rounded transition-colors hover:bg-secondary text-muted-foreground hover:text-primary`}
            onClick={(e) => {
              e.stopPropagation();
              handleClickRefine();
            }}
            title="Refine rubric"
          >
            <PickaxeIcon className="h-3 w-3" />
          </button>
        )} */}
        <button
          className={`p-1.5 rounded transition-colors
            ${
              hasActiveJob
                ? 'bg-orange-bg text-orange-text'
                : 'hover:bg-green-bg/50 text-muted-foreground hover:text-green-text'
            }`}
          onClick={(e) => {
            e.stopPropagation();
            if (hasActiveJob && jobDetails) {
              handleCancelJob(jobDetails.id);
            } else {
              startEvaluation({
                collectionId,
                rubricId: rubric.id,
              });
            }
          }}
          title={hasActiveJob ? 'Cancel job' : 'Evaluate with this rubric'}
          disabled={isCancellingJob}
        >
          {hasActiveJob ? (
            <Pause className="h-3 w-3" />
          ) : (
            <Play className="h-3 w-3" />
          )}
        </button>
        {hasWritePermission && (
          <button
            className="p-1.5 rounded transition-colors hover:bg-red-bg/50 text-muted-foreground hover:text-red-text"
            onClick={(e) => {
              e.stopPropagation();
              handleDelete(rubric.id);
            }}
            title="Delete rubric"
            disabled={isDeletingRubric}
          >
            <Trash2 className="h-3 w-3" />
          </button>
        )}
      </div>
    </div>
  );
}

export default function RubricList() {
  const dispatch = useAppDispatch();

  const collectionId = useAppSelector((state) => state.collection.collectionId);
  const rubricsMap = useAppSelector((state) => state.rubric.latestRubricsMap);

  // Check write permissions
  const hasWritePermission = useHasCollectionWritePermission();

  // Fetch rubrics using the new API
  const { data: fetchedRubrics, isLoading: isLoadingRubrics } =
    useGetRubricsQuery(
      { collectionId: collectionId! },
      { skip: !collectionId }
    );

  const [createRubric, { isLoading: isCreatingRubric }] =
    useCreateRubricMutation();
  const [startEvaluation] = useStartEvaluationMutation();

  const rubrics = Object.values(rubricsMap);

  const handleAddNew = async () => {
    if (!collectionId) return;

    try {
      // Create a new rubric using the API
      const newRubric = {
        high_level_description: '',
        inclusion_rules: [],
        exclusion_rules: [],
      };

      await createRubric({
        collectionId,
        rubric: newRubric,
      }).unwrap();

      // The rubric will be automatically added to the store via extraReducers
    } catch (error) {
      console.error('Failed to create rubric:', error);
      toast({
        title: 'Error',
        description: 'Failed to create rubric',
        variant: 'destructive',
      });
    }
  };

  return (
    <div className="space-y-2">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex flex-col">
          <div className="text-sm font-semibold">Saved Rubrics</div>
          <div className="text-xs text-muted-foreground">
            Run and modify previously-created rubrics
          </div>
        </div>
        {hasWritePermission && (
          <Button
            onClick={handleAddNew}
            size="sm"
            variant="outline"
            className="h-7 gap-1 text-xs"
            disabled={isCreatingRubric}
          >
            <Plus className="h-3 w-3 -ml-1" />
            {isCreatingRubric ? 'Creating...' : 'Rubric'}
          </Button>
        )}
      </div>

      {/* Rubrics List */}
      <div className="space-y-1.5">
        {isLoadingRubrics ? (
          <div className="text-xs text-muted-foreground text-center py-4">
            Loading rubrics...
          </div>
        ) : rubrics.length === 0 ? (
          <div className="text-xs text-muted-foreground text-center py-4">
            No rubrics created yet
          </div>
        ) : (
          rubrics.map((rubric) => (
            <RubricCard
              key={rubric.id}
              rubric={rubric}
              collectionId={collectionId!}
              hasWritePermission={hasWritePermission}
            />
          ))
        )}
      </div>
    </div>
  );
}
