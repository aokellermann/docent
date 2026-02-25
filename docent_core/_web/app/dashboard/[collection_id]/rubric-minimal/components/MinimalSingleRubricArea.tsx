'use client';

import { useCallback, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import { useHasCollectionWritePermission } from '@/lib/permissions/hooks';
import { useGetAgentRunMetadataQuery } from '@/app/api/collectionApi';

import { Rubric } from '../../../../store/rubricSlice';

import {
  Loader2,
  Tags,
  ChevronRight,
  FunnelPlus,
  Copy,
  FileCode,
  Link,
} from 'lucide-react';
import MinimalRubricEditor, {
  RubricVersionNavigator,
} from './MinimalRubricEditor';
import { MinimalJudgeResultsList } from './MinimalJudgeResultsList';
import {
  AgentRunJudgeResults,
  useGetRubricQuery,
  useGetLatestRubricVersionQuery,
  useUpdateRubricMutation,
} from '../../../../api/rubricApi';
import { useFilterFields } from '@/hooks/use-filter-fields';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import LabelSetsDialog from '../../components/LabelSetsDialog';
import { AgreementPopover } from '../../components/AgreementPopover';
import ClusterButton from '../../components/ClusterButton';
import useJobStatus from '@/app/hooks/use-job-status';
import { ProgressBar } from '@/app/components/ProgressBar';
import { useRubricVersion } from '@/providers/use-rubric-version';
import { toast } from 'sonner';
import { Label, useGetLabelsInLabelSetQuery } from '@/app/api/labelApi';
import { useLabelSets } from '@/providers/use-label-sets';
import { skipToken } from '@reduxjs/toolkit/query';
import { SchemaDefinition } from '@/app/types/schema';
import { cn } from '@/lib/utils';
import UuidPill from '@/components/UuidPill';
import { FilterControls } from '@/app/components/FilterControls';
import { FilterChips } from '@/app/components/FilterChips';
import { FilterActionsBar } from '@/app/components/FilterActionsBar';
import { ComplexFilter, PrimitiveFilter } from '@/app/types/collectionTypes';
import ViewModeDropdown from '../../components/ViewModeDropdown';
import { ViewMode } from '../../utils/viewModeResults';
import DownloadMenu from '@/app/components/DownloadMenu';
import { BASE_URL } from '@/app/constants';
import { useDownloadApiKey } from '@/app/hooks/use-download-api-key';
import {
  API_KEY_PLACEHOLDER,
  downloadPythonSample,
  fetchPythonSample,
} from '@/app/utils/pythonSamples';
import { copyDqlToClipboard } from '@/app/utils/copyDql';

interface AgreementWidgetProps {
  agentRunResults: AgentRunJudgeResults[];
  activeLabelSet: any;
  setIsLabelSetsDialogOpen: (open: boolean) => void;
  labels: Label[];
  schema?: SchemaDefinition;
  className?: string;
  activeFilters: any[];
}

function AgreementWidget({
  agentRunResults,
  activeLabelSet,
  setIsLabelSetsDialogOpen,
  labels,
  schema,
  className,
  activeFilters,
}: AgreementWidgetProps) {
  return (
    <div className={cn('flex flex-row', className)}>
      <TooltipProvider>
        <div className="flex">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setIsLabelSetsDialogOpen(true)}
              >
                <Tags />
                {activeLabelSet ? (
                  <span className="hidden xl:inline">
                    {activeLabelSet.name}
                  </span>
                ) : (
                  <span className="hidden xl:inline">Select label set</span>
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent>Manage label sets</TooltipContent>
          </Tooltip>
        </div>
      </TooltipProvider>
      {activeLabelSet && (
        <AgreementPopover
          agentRunResults={agentRunResults}
          labels={labels}
          schema={schema}
          activeFilters={activeFilters}
        />
      )}
    </div>
  );
}

interface MinimalSingleRubricAreaProps {
  rubricId: string;
}

export default function MinimalSingleRubricArea({
  rubricId,
}: MinimalSingleRubricAreaProps) {
  const isMinimalMode = true;
  const mode = 'minimal';
  const routeBase: 'rubric' | 'rubric-minimal' = 'rubric-minimal';
  const {
    collection_id: collectionId,
    result_id: resultId,
    agent_run_id: agentRunId,
  } = useParams<{
    collection_id: string;
    result_id?: string;
    agent_run_id?: string;
  }>();

  const [updateRubric] = useUpdateRubricMutation();
  const hasWritePermission = useHasCollectionWritePermission();

  const { activeLabelSet, setLabelSet: setActiveLabelSet } =
    useLabelSets(rubricId);
  const activeLabelSetId = isMinimalMode ? null : activeLabelSet?.id;

  // Unsaved changes from the editor
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const { version, setVersion } = useRubricVersion();

  // Filter and view mode state
  const [runsFilter, setRunsFilter] = useState<ComplexFilter | null>(null);
  const [filterPopoverOpen, setFilterPopoverOpen] = useState(false);
  const [editingFilter, setEditingFilter] = useState<PrimitiveFilter | null>(
    null
  );
  const [viewMode, setViewMode] = useState<ViewMode>('all');
  const [showFailures, setShowFailures] = useState(false);

  const { fields: agentRunMetadataFields } = useFilterFields({
    collectionId,
    context: { mode: 'judge_results', rubricId, rubricVersion: version },
  });

  const {
    // Rubric job status
    rubricJobId,
    rubricJobStatus,
    totalResultsNeeded,
    currentResultsCount,

    // Rubric run results
    agentRunResults: agentRunResultsAll,
    failureCount,

    // Clustering job status
    clusteringJobId,
    clusteringJobStatus,
    centroids,

    // Clustering results
    assignments,
    // Loading flags
    isResultsLoading,
  } = useJobStatus({
    collectionId,
    rubricId,
    labelSetId: activeLabelSetId ?? null,
    filter: isMinimalMode ? null : runsFilter,
  });

  // Filter out failures if not showing them
  const agentRunResults = showFailures
    ? agentRunResultsAll
    : agentRunResultsAll
        .map((run) => ({
          // This logic filters out the failures from the results of this agent run
          // Prevents issue where, if an agent run has both successes and failures, the failures slip through
          ...run,
          results:
            run.results?.filter(
              (result) => result.result_type === 'DIRECT_RESULT'
            ) ?? [],
        }))
        .filter((run) => run.results.length > 0);

  // In minimal mode, filter to only show matches by default
  const [showOnlyMatches, setShowOnlyMatches] = useState(isMinimalMode);
  const filteredAgentRunResults = showOnlyMatches
    ? agentRunResults
        .map((run) => ({
          ...run,
          results: run.results.filter(
            (result) => result.output?.label === 'match'
          ),
        }))
        .filter((run) => run.results.length > 0)
    : agentRunResults;

  // In minimal mode, fetch target_model metadata for each agent run
  const allAgentRunIds = useMemo(
    () => filteredAgentRunResults.map((r) => r.agent_run_id),
    [filteredAgentRunResults]
  );
  const { data: metadataMap } = useGetAgentRunMetadataQuery(
    isMinimalMode && allAgentRunIds.length > 0
      ? {
          collectionId,
          agent_run_ids: allAgentRunIds,
          fields: ['target_model'],
        }
      : skipToken
  );
  const modelByAgentRunId = useMemo(() => {
    if (!metadataMap) return {};
    const map: Record<string, string> = {};
    for (const [agentRunId, entry] of Object.entries(metadataMap)) {
      const meta = (entry as Record<string, unknown>)?.metadata;
      const model = (meta as Record<string, unknown>)?.target_model;
      map[agentRunId] = typeof model === 'string' ? model : 'Unknown';
    }
    return map;
  }, [metadataMap]);

  // Get the remote rubric
  const { data: rubric } = useGetRubricQuery({
    collectionId,
    rubricId,
    version,
  });
  const schema = rubric?.output_schema;

  const { data: labels = [], isLoading: isLabelsLoading } =
    useGetLabelsInLabelSetQuery(
      !isMinimalMode && activeLabelSet
        ? { collectionId, labelSetId: activeLabelSet.id }
        : skipToken
    );
  const hasLabels = (labels?.length ?? 0) > 0;

  const { getApiKey: getDownloadApiKey, isLoading: isApiKeyLoading } =
    useDownloadApiKey();
  const [isDownloadingSample, setIsDownloadingSample] = useState(false);
  const [isCopyingDql, setIsCopyingDql] = useState(false);
  const [isLabelSetsDialogOpen, setIsLabelSetsDialogOpen] = useState(false);

  const handleImportLabelSet = (labelSet: any) => {
    setActiveLabelSet(labelSet);
  };

  const handleRubricSave = async (
    rubric: Rubric,
    clearLabels: boolean = false
  ) => {
    // Just unlink the labels from the current rubric.
    if (hasLabels && clearLabels) {
      setActiveLabelSet(null);
    }

    try {
      await updateRubric({
        collectionId,
        rubricId,
        rubric,
      }).unwrap();
      setVersion(rubric.version);
    } catch (error) {
      console.error('Failed to update rubric in minimal flow', error);
      toast.error('Failed to save rubric');
    }
  };

  const [isEditorCollapsed, setIsEditorCollapsed] = useState(false);

  // Get the latest version number for the version navigator
  const minVersion = 1;
  const { data: maxVersion } = useGetLatestRubricVersionQuery({
    collectionId,
    rubricId,
  });

  // Determine if the editor is editable
  const isEditable =
    !rubricJobId && hasWritePermission && !clusteringJobId && !isLabelsLoading;

  const isClusteringActive = clusteringJobId !== null || centroids.length > 0;

  const handleRunsFilterChange = (filters: ComplexFilter | null) => {
    setRunsFilter(filters);
    setEditingFilter(null);
    setFilterPopoverOpen(false);
  };

  const handleRequestEditFilter = (filter: PrimitiveFilter) => {
    setEditingFilter(filter);
    setFilterPopoverOpen(true);
  };

  const handleDownloadRubricSample = useCallback(
    async (format: 'python' | 'notebook' = 'python') => {
      if (!collectionId) {
        toast.error('Open a collection before downloading a code sample.');
        return;
      }

      try {
        setIsDownloadingSample(true);
        const apiKey = await getDownloadApiKey();
        await downloadPythonSample({
          type: 'rubric_results',
          api_key: apiKey,
          server_url: BASE_URL,
          collection_id: collectionId,
          rubric_id: rubricId,
          rubric_version: version ?? null,
          runs_filter: runsFilter ?? null,
          format,
        });
      } catch (error) {
        console.error('Failed to download rubric Python sample', error);
        toast.error('Unable to generate a Python sample for this rubric.');
      } finally {
        setIsDownloadingSample(false);
      }
    },
    [
      agentRunResults.length,
      collectionId,
      getDownloadApiKey,
      rubricId,
      runsFilter,
      version,
    ]
  );

  const handleCopyRubricDql = useCallback(async () => {
    if (!collectionId) {
      toast.error('Open a collection before copying DQL.');
      return;
    }

    try {
      setIsCopyingDql(true);
      const sample = await fetchPythonSample({
        type: 'rubric_results',
        api_key: API_KEY_PLACEHOLDER,
        server_url: BASE_URL,
        collection_id: collectionId,
        rubric_id: rubricId,
        rubric_version: version ?? null,
        runs_filter: runsFilter ?? null,
        format: 'python',
      });

      await copyDqlToClipboard(sample.dql_query);
    } catch (error) {
      console.error('Failed to copy rubric DQL', error);
      toast.error('Unable to copy DQL for this rubric.');
    } finally {
      setIsCopyingDql(false);
    }
  }, [collectionId, rubricId, runsFilter, version]);

  const defaultResultsSection = (
    <>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
        <div className="inline-flex items-center border border-border rounded-md overflow-hidden">
          <ViewModeDropdown
            agentRunResults={agentRunResults}
            labels={labels ?? []}
            className="!border-0 rounded-r-none rounded-l-md shadow-none"
            viewMode={viewMode}
            setViewMode={setViewMode}
          />
          <div className="h-7 w-px bg-border" />
          <Popover open={filterPopoverOpen} onOpenChange={setFilterPopoverOpen}>
            <Tooltip>
              <TooltipTrigger asChild>
                <PopoverTrigger asChild>
                  <Button className="inline-flex items-center h-7 gap-x-1 text-xs bg-background text-muted-foreground hover:text-primary px-1.5 hover:bg-accent transition-all duration-200 rounded-l-none rounded-r-md">
                    <FunnelPlus size={14} className="stroke-[1.5]" />
                  </Button>
                </PopoverTrigger>
              </TooltipTrigger>
              <TooltipContent>
                <p>Add filter</p>
              </TooltipContent>
            </Tooltip>
            <PopoverContent
              align="start"
              sideOffset={4}
              className="w-[520px] overflow-x-auto space-y-1.5"
            >
              <FilterControls
                filters={runsFilter}
                onFiltersChange={handleRunsFilterChange}
                metadataFields={agentRunMetadataFields}
                collectionId={collectionId!}
                showStepFilter={false}
                initialFilter={editingFilter}
              />
            </PopoverContent>
          </Popover>
        </div>
        {hasWritePermission && (
          <FilterActionsBar
            collectionId={collectionId!}
            surfaceId={`rubric-results:${rubricId}`}
            currentFilter={runsFilter}
            onApplyFilter={handleRunsFilterChange}
            onClearFilter={() => handleRunsFilterChange(null)}
          />
        )}
        {runsFilter && (
          <FilterChips
            filters={runsFilter}
            onFiltersChange={handleRunsFilterChange}
            onRequestEdit={handleRequestEditFilter}
            readOnly={!hasWritePermission}
          />
        )}
        {failureCount > 0 && (
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <Switch
              id="include-failures"
              checked={showFailures}
              onCheckedChange={setShowFailures}
              className="scale-75"
            />
            <label htmlFor="include-failures" className="cursor-pointer">
              Show <span className="text-red-500">{failureCount} errors</span>
            </label>
          </div>
        )}
        <div className="flex items-center gap-1.5 ml-auto">
          {!rubricJobId &&
            hasWritePermission &&
            agentRunResultsAll.some((run) =>
              run.results?.some((r) => r.result_type === 'DIRECT_RESULT')
            ) && (
              <ClusterButton
                collectionId={collectionId}
                rubricId={rubricId}
                clusteringJobId={clusteringJobId}
                clusteringJobStatus={clusteringJobStatus}
                hasUnsavedChanges={hasUnsavedChanges}
                hasCentroids={centroids.length > 0}
              />
            )}
          {!isClusteringActive && (
            <AgreementWidget
              agentRunResults={agentRunResults}
              activeLabelSet={activeLabelSet}
              setIsLabelSetsDialogOpen={setIsLabelSetsDialogOpen}
              schema={schema}
              labels={labels ?? []}
              activeFilters={runsFilter?.filters ?? []}
            />
          )}
          <DownloadMenu
            options={[
              {
                key: 'python',
                label: 'Python',
                disabled: isDownloadingSample || isApiKeyLoading,
                icon:
                  isDownloadingSample || isApiKeyLoading ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <FileCode className="h-3 w-3" />
                  ),
                onSelect: () => {
                  void handleDownloadRubricSample('python');
                },
              },
              {
                key: 'notebook',
                label: 'Notebook',
                disabled: isDownloadingSample || isApiKeyLoading,
                icon:
                  isDownloadingSample || isApiKeyLoading ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <FileCode className="h-3 w-3" />
                  ),
                onSelect: () => {
                  void handleDownloadRubricSample('notebook');
                },
              },
              {
                key: 'copy_dql',
                label: 'Copy DQL',
                disabled:
                  isCopyingDql || isDownloadingSample || isApiKeyLoading,
                icon:
                  isCopyingDql || isApiKeyLoading ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Copy className="h-3 w-3" />
                  ),
                onSelect: () => {
                  void handleCopyRubricDql();
                },
              },
            ]}
            isLoading={isDownloadingSample || isApiKeyLoading || isCopyingDql}
            triggerDisabled={
              isDownloadingSample || isApiKeyLoading || isCopyingDql
            }
            className="h-7 gap-1 text-xs"
            contentClassName="w-36"
          />
        </div>
      </div>

      {rubricJobId && (
        <ProgressBar
          current={currentResultsCount}
          total={totalResultsNeeded}
          paused={false}
        />
      )}

      {/* Clustering loader (non-blocking) */}
      {clusteringJobId !== null && (
        <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground px-0.5">
          <Loader2 size={16} className="animate-spin text-muted-foreground" />
          Clustering results...
        </div>
      )}

      {/* Results */}
      {isResultsLoading || !schema ? (
        <div className="flex items-center justify-center">
          <Loader2 size={16} className="animate-spin text-muted-foreground" />
        </div>
      ) : !rubricJobId && agentRunResults.length === 0 ? (
        <div className="text-xs text-muted-foreground text-center">
          No results yet
        </div>
      ) : (
        <MinimalJudgeResultsList
          labels={labels ?? []}
          centroids={centroids}
          assignments={assignments}
          agentRunResults={agentRunResults}
          isClusteringActive={clusteringJobId !== null}
          activeResultId={resultId}
          activeAgentRunId={agentRunId}
          schema={schema}
          activeLabelSet={activeLabelSet}
          viewMode={viewMode}
          routeBase={routeBase}
        />
      )}
    </>
  );

  // Per-model result count breakdown for minimal mode
  const modelCountSummary = useMemo(() => {
    if (!metadataMap) return null;
    const counts: Record<string, number> = {};
    for (const run of filteredAgentRunResults) {
      const model = modelByAgentRunId[run.agent_run_id] ?? 'Unknown';
      counts[model] = (counts[model] ?? 0) + run.results.length;
    }
    return Object.entries(counts)
      .sort(([, a], [, b]) => b - a)
      .map(([model, count]) => `${count} ${model}`)
      .join(', ');
  }, [filteredAgentRunResults, metadataMap, modelByAgentRunId]);

  const totalFilteredResults = filteredAgentRunResults.reduce(
    (acc, r) => acc + r.results.length,
    0
  );

  const handleCopyLink = useCallback(() => {
    navigator.clipboard.writeText(window.location.href).then(() => {
      toast.success('Link copied to clipboard');
    });
  }, []);

  const minimalResultsSection = (
    <>
      {rubricJobId && (
        <ProgressBar
          current={currentResultsCount}
          total={totalResultsNeeded}
          paused={false}
        />
      )}

      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">
          {modelCountSummary ?? `${totalFilteredResults} results`}
        </span>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="h-6 gap-1 px-1.5 text-xs text-muted-foreground"
            onClick={handleCopyLink}
          >
            <Link size={12} />
            Copy link
          </Button>
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            Matches only
            <Switch
              checked={showOnlyMatches}
              onCheckedChange={setShowOnlyMatches}
              className="scale-75"
            />
          </label>
        </div>
      </div>

      {isResultsLoading || !schema ? (
        <div className="flex items-center justify-center">
          <Loader2 size={16} className="animate-spin text-muted-foreground" />
        </div>
      ) : !rubricJobId && filteredAgentRunResults.length === 0 ? (
        <div className="text-xs text-muted-foreground text-center">
          No results yet
        </div>
      ) : (
        <MinimalJudgeResultsList
          labels={[]}
          centroids={[]}
          assignments={{}}
          agentRunResults={filteredAgentRunResults}
          isClusteringActive={false}
          activeResultId={resultId}
          activeAgentRunId={agentRunId}
          schema={schema}
          activeLabelSet={null}
          viewMode="all"
          showLabels={false}
          routeBase={routeBase}
          metadataByAgentRunId={modelByAgentRunId}
        />
      )}
    </>
  );

  return (
    <div className="space-y-2 flex flex-col flex-1 min-w-0 min-h-0">
      {/* Clickable header with disclosure triangle */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="flex items-center gap-1 cursor-pointer hover:text-foreground/80"
            onClick={() => setIsEditorCollapsed(!isEditorCollapsed)}
            aria-expanded={!isEditorCollapsed}
          >
            <ChevronRight
              className={cn(
                'h-4 w-4 transition-transform',
                !isEditorCollapsed && 'rotate-90'
              )}
            />
            <span className="text-sm font-semibold">Rubric</span>
          </button>
          {!isMinimalMode && (
            <UuidPill uuid={rubricId} stopPropagation={true} />
          )}
        </div>

        {!isMinimalMode && (
          <RubricVersionNavigator
            rubric={rubric}
            maxVersion={maxVersion}
            minVersion={minVersion}
            setRubricVersion={setVersion}
          />
        )}
      </div>

      {!isEditorCollapsed && (
        <MinimalRubricEditor
          collectionId={collectionId}
          rubricId={rubricId}
          rubricVersion={version}
          onSave={handleRubricSave}
          onCloseWithoutSave={() => {}}
          shouldConfirmOnSave={!isMinimalMode && hasLabels}
          onHasUnsavedChangesUpdated={setHasUnsavedChanges}
          editable={isEditable}
          mode={mode}
        />
      )}

      {isMinimalMode ? minimalResultsSection : defaultResultsSection}

      {!isMinimalMode && (
        <LabelSetsDialog
          open={isLabelSetsDialogOpen}
          onOpenChange={setIsLabelSetsDialogOpen}
          onImportLabelSet={handleImportLabelSet}
          onClearActiveLabelSet={() => setActiveLabelSet(null)}
          currentRubricSchema={schema}
          activeLabelSetId={activeLabelSet?.id}
        />
      )}
    </div>
  );
}
