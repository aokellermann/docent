import { useGetAgentRunMetadataFieldsQuery } from '@/app/api/collectionApi';
import { useGetJudgeResultFilterFieldsQuery } from '@/app/api/rubricApi';
import { TranscriptMetadataField } from '@/app/types/experimentViewerTypes';

/**
 * Mode for fetching filter fields.
 *
 * - 'agent_runs': Fetches fields for filtering agent runs (used by Agent Run Table, Charts, Rubric Run Config)
 * - 'judge_results': Fetches fields scoped to a specific rubric's judge results (used by Rubric Results view)
 */
export type FilterFieldsMode =
  | { mode: 'agent_runs' }
  | { mode: 'judge_results'; rubricId: string; rubricVersion?: number | null };

export interface UseFilterFieldsOptions {
  collectionId: string | undefined;
  context: FilterFieldsMode;
}

export interface UseFilterFieldsResult {
  fields: TranscriptMetadataField[];
  isLoading: boolean;
  error: unknown;
}

/**
 * Hook to fetch filter fields based on the context.
 *
 * Provides a unified interface for fetching filter fields regardless of whether
 * you're filtering agent runs or judge results.
 *
 * @example
 * // For Agent Run Table, Charts, Rubric Run Config
 * const { fields } = useFilterFields({
 *   collectionId,
 *   context: { mode: 'agent_runs' }
 * });
 *
 * @example
 * // For Rubric Results view
 * const { fields } = useFilterFields({
 *   collectionId,
 *   context: { mode: 'judge_results', rubricId, rubricVersion: version }
 * });
 */
export function useFilterFields({
  collectionId,
  context,
}: UseFilterFieldsOptions): UseFilterFieldsResult {
  const isAgentRunsMode = context.mode === 'agent_runs';
  const isJudgeResultsMode = context.mode === 'judge_results';

  // Agent runs mode - uses the general metadata fields API
  const agentRunsQuery = useGetAgentRunMetadataFieldsQuery(collectionId!, {
    skip: !collectionId || !isAgentRunsMode,
  });

  // Judge results mode - uses the rubric-scoped API
  const judgeResultsQuery = useGetJudgeResultFilterFieldsQuery(
    {
      collectionId: collectionId!,
      rubricId: isJudgeResultsMode ? context.rubricId : '',
      version: isJudgeResultsMode ? context.rubricVersion : undefined,
    },
    { skip: !collectionId || !isJudgeResultsMode }
  );

  if (isAgentRunsMode) {
    return {
      fields: agentRunsQuery.data?.fields ?? [],
      isLoading: agentRunsQuery.isLoading,
      error: agentRunsQuery.error,
    };
  }

  return {
    fields: judgeResultsQuery.data?.fields ?? [],
    isLoading: judgeResultsQuery.isLoading,
    error: judgeResultsQuery.error,
  };
}
