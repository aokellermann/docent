import { ChevronDown, ChevronRight, Loader2, ChevronLeft, ChevronFirst, ChevronLast } from 'lucide-react';
import React, {
  useMemo,
  useState,
  useEffect,
  useCallback,
} from 'react';
import { useRouter } from 'next/navigation';

import { Card } from '@/components/ui/card';

import { useAppDispatch, useAppSelector } from '../store/hooks';
import { PrimitiveFilter } from '../types/frameTypes';

import DimensionSelector from './DimensionSelector';
import { AgentRunMetadata } from './AgentRunMetadata';
import { Citation } from '../types/experimentViewerTypes';
import { RegexSnippet } from '../types/experimentViewerTypes';
import { navToAgentRun } from '@/lib/nav';
import { renderTextWithCitations } from '@/lib/renderCitations';
import { RootState } from '../store/store';
import { SearchResultWithCitations } from '../types/frameTypes';
import { addBaseFilter, addBaseFilters, updateBaseFilter } from '../store/searchSlice';

// Constants for magic numbers
const PAGINATION_LIMIT = 100;
const MAX_DIMENSION_VALUES = 100;
const HIGH_SCORE_THRESHOLD = 0.8;
const LOW_SCORE_THRESHOLD = 0;

const getScoreFromStats = (stats: any) => {
  if (!stats) return { score: 0 };
  const scoreKey = Object.keys(stats).find(k => k.toLowerCase().includes('default')) || Object.keys(stats)[0];
  if (!scoreKey || stats[scoreKey]?.mean === undefined || stats[scoreKey].mean === null) {
    return { score: 0 };
  }
  return {
    score: stats[scoreKey].mean as number,
    n: stats[scoreKey].n,
    ci: stats[scoreKey].ci
  };
};

const getScoreDisplay = (score: number | undefined, ci?: number) => {
  if (typeof score !== 'number') return '';
  let display = score.toFixed(2);
  if (ci && ci > 0) display += ` ±${ci.toFixed(3)}`;
  return display;
};

const getScoreClass = (score: number | undefined) => {
  if (typeof score !== 'number') return 'bg-red-50';
  if (score >= HIGH_SCORE_THRESHOLD) return 'bg-green-50';
  if (score > LOW_SCORE_THRESHOLD) return 'bg-yellow-50';
  return 'bg-red-50';
};

const getFilterTitle = (rowName: string, rowValue: string, colName?: string, colValue?: string) => {
  if (colName && colValue) {
    return `Filter to ${rowName}: ${rowValue}, ${colName}: ${colValue}`;
  }
  return `Filter to ${rowName}: ${rowValue}`;
};

interface AttributeSectionProps {
  dataId: string;
  curAttributeQuery: string;
  attributes: SearchResultWithCitations[];
}

const AttributeSection: React.FC<AttributeSectionProps> = ({
  dataId,
  curAttributeQuery,
  attributes,
}) => {
  const router = useRouter();
  const frameGridId = useAppSelector((state: RootState) => state.frame.frameGridId);

  if (attributes.length === 0) {
    return null;
  }

  return (
    <div className="pt-1 mt-1 border-t border-indigo-100 text-xs space-y-1">
      <div className="flex items-center mb-1">
        <div className="h-2 w-2 rounded-full bg-indigo-500 mr-1.5"></div>
        <span className="text-xs font-medium text-indigo-700">
          Attributes from your query
        </span>
      </div>
      {attributes.map((attribute, idx) => {
        const attributeText = attribute.value;
        if (!attributeText) {
          return null;
        }
        const citations = attribute.citations || [];
        return (
          <div
            key={idx}
            className="group bg-indigo-50 rounded-md p-1 text-xs text-indigo-900 leading-snug mt-1 hover:bg-indigo-100 transition-colors cursor-pointer border border-transparent hover:border-indigo-200"
            onMouseDown={(e) => {
              const firstCitation = citations.length > 0 ? citations[0] : null;
              navToAgentRun(
                e,
                router,
                window,
                dataId,
                firstCitation?.transcript_idx ?? undefined,
                firstCitation?.block_idx,
                frameGridId,
                curAttributeQuery
              );
            }}
          >
            <div className="flex flex-col">
              <div className="flex items-start justify-between gap-2">
                <p className="mb-0.5 flex-1">
                  {renderTextWithCitations(
                    attributeText,
                    citations,
                    dataId,
                    router,
                    window,
                    curAttributeQuery,
                    frameGridId
                  )}
                </p>
                <div className="flex shrink-0"></div>
              </div>
              <div className="flex items-center gap-1 text-[10px] text-indigo-600 mt-1">
                <span className="opacity-70">{curAttributeQuery}</span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

const HighlightedSnippet: React.FC<{ snippetData: RegexSnippet }> = ({ snippetData }) => {
  const [isExpanded, setIsExpanded] = React.useState(false);
  try {
    if (!snippetData || typeof snippetData !== 'object') {
      return <p className="text-xs text-red-600">Error: Invalid snippet data</p>;
    }
    const { snippet, match_start, match_end } = snippetData;
    if (
      typeof snippet !== 'string' ||
      typeof match_start !== 'number' ||
      typeof match_end !== 'number'
    ) {
      return <p className="text-xs text-red-600">Error: Invalid snippet format</p>;
    }
    if (
      match_start < 0 ||
      match_end > snippet.length ||
      match_start >= match_end
    ) {
      return <p className="text-xs">{snippet}</p>;
    }
    const before = snippet.substring(0, match_start);
    const matched = snippet.substring(match_start, match_end);
    const after = snippet.substring(match_end);
    return (
      <div
        className="bg-indigo-50 p-2 rounded-md border border-transparent hover:border-indigo-200 max-w-full cursor-pointer transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div
          className={`overflow-y-auto ${isExpanded ? '' : 'max-h-20'}`}
          style={{ scrollbarWidth: 'thin', scrollbarColor: '#a5b3e6 #e0e7ff' }}
        >
          <span className="text-xs text-indigo-900 break-words whitespace-pre-wrap">
            {before}
            <span className="px-0.5 py-0.25 bg-indigo-200 text-indigo-800 rounded">{matched}</span>
            {after}
          </span>
        </div>
      </div>
    );
  } catch (error) {
    return <p className="text-xs text-red-600">Error rendering snippet</p>;
  }
};

const RegexSnippetsSection: React.FC<{ regexSnippets?: RegexSnippet[] }> = ({ regexSnippets }) => {
  if (!regexSnippets || regexSnippets.length === 0) {
    return null;
  }
  return (
    <div className="border-indigo-100 border-t pt-1 mt-1 space-y-1">
      <div className="flex items-center">
        <div className="h-2 w-2 rounded-full bg-indigo-500 mr-1.5"></div>
        <span className="text-xs font-medium text-indigo-700">Regex matches</span>
      </div>
      {regexSnippets?.map((snippetData, index) => (
        <HighlightedSnippet key={index} snippetData={snippetData} />
      ))}
    </div>
  );
};

export default function ExperimentViewer() {
  const dispatch = useAppDispatch();
  const router = useRouter();
  
  // Get all state at the top level
  const { innerDimId, outerDimId, dimensionsMap, agentRunMetadata, frameGridId, baseFilter } = useAppSelector(
    (state) => state.frame
  );

  const {
    loadingSearchQuery,
    curSearchQuery,
    searchResultMap: attributeMap,
  } = useAppSelector((state) => state.search);

  const {
    experimentViewerScrollPosition,
    dimIdsToFilterIds,
    filtersMap,
    regexSnippets,
    statMarginals: rawStatMarginals,
    idMarginals: rawIdMarginals,
  } = useAppSelector((state) => state.experimentViewer);

  // Create a function to get the marginal key - safe to use even if data is null
  const getMarginalKey = useCallback(
    (innerId: string | null, outerId: string | null) => {
      if (innerId !== null && outerId !== null) {
        return `${innerDimId},${innerId}|${outerDimId},${outerId}`;
      } else if (innerId !== null) {
        return `${innerDimId},${innerId}`;
      } else if (outerId !== null) {
        return `${outerDimId},${outerId}`;
      } else {
        return '';
      }
    },
    [innerDimId, outerDimId]
  );

  // Filter to IDs to ones that have the attribute query
  const idMarginals = useMemo(() => {
    if (!rawIdMarginals) return rawIdMarginals;
    if (!curSearchQuery) return rawIdMarginals;

    // Filter the keys and their datapoints based on attribute query
    const filtered = Object.entries(rawIdMarginals).reduce(
      (result, [key, datapointsList]) => {
        // Filter datapoints to ones that have the attributes
        const filteredAgentRuns = datapointsList.filter((datapointId) => {
          if (curSearchQuery) {
            const attrs = attributeMap?.[datapointId]?.[curSearchQuery];
            return attrs && attrs.length && attrs[0].value !== null;
          }
          return true;
        });

        // Only include keys that have at least one datapoint after filtering
        if (filteredAgentRuns.length > 0) {
          result[key] = filteredAgentRuns;
        }

        return result;
      },
      {} as typeof rawIdMarginals
    );

    return filtered;
  }, [rawIdMarginals, curSearchQuery, attributeMap]);

  // Only keep stat marginals that have datapoints, after filtering by attribute query
  const statMarginals = useMemo(() => {
    if (!rawStatMarginals) return rawStatMarginals;
    if (!curSearchQuery) return rawStatMarginals;
    return Object.fromEntries(
      Object.entries(rawStatMarginals).filter(([key, _]) => {
        return idMarginals && key in idMarginals;
      })
    );
  }, [rawStatMarginals, curSearchQuery, idMarginals]);

  // FLAT LIST: Collect all agent runs (datapoint IDs) from idMarginals
  const allAgentRunEntries: [string, string[]][] = useMemo(() => {
    if (!idMarginals) return [];
    return Object.entries(idMarginals);
  }, [idMarginals]);

  // Flatten agent run entries for pagination
  const flatAgentRuns = useMemo(() => {
    const result: { agentRunId: string; marginalKey: string }[] = [];
    allAgentRunEntries.forEach(([marginalKey, agentRunIds]) => {
      agentRunIds.forEach(agentRunId => {
        result.push({ agentRunId, marginalKey });
      });
    });
    return result;
  }, [allAgentRunEntries]);

  // Get unique outer and inner dimension values with their IDs
  const outerValuesWithIds = useMemo(() => {
    if (!outerDimId || !filtersMap || !dimIdsToFilterIds) return [];
    const allValues = dimIdsToFilterIds[outerDimId]?.map(id => ({
      id,
      value: filtersMap[id].value
    })) || [];
    return allValues.slice(0, MAX_DIMENSION_VALUES);
  }, [outerDimId, filtersMap, dimIdsToFilterIds]);

  const innerValuesWithIds = useMemo(() => {
    if (!innerDimId || !filtersMap || !dimIdsToFilterIds) return [];
    const allValues = dimIdsToFilterIds[innerDimId]?.map(id => ({
      id,
      value: filtersMap[id].value
    })) || [];
    return allValues.slice(0, MAX_DIMENSION_VALUES);
  }, [innerDimId, filtersMap, dimIdsToFilterIds]);

  // Get total counts for UI indicators
  const totalOuterValues = useMemo(() => {
    if (!outerDimId || !filtersMap || !dimIdsToFilterIds) return 0;
    return dimIdsToFilterIds[outerDimId]?.length || 0;
  }, [outerDimId, filtersMap, dimIdsToFilterIds]);

  const totalInnerValues = useMemo(() => {
    if (!innerDimId || !filtersMap || !dimIdsToFilterIds) return 0;
    return dimIdsToFilterIds[innerDimId]?.length || 0;
  }, [innerDimId, filtersMap, dimIdsToFilterIds]);

  // Helper to safely get dimension name
  const getDimensionName = (dimId: string | undefined) => {
    if (!dimId || !dimensionsMap) return 'Dimension';
    return dimensionsMap[dimId]?.name ?? 'Dimension';
  };

  const tableData = useMemo(() => {
    const hasOuter = outerValuesWithIds.length > 0;
    const hasInner = innerValuesWithIds.length > 0;
    
    if (!hasOuter && !hasInner) return null;
    
    // 2D case: outer as rows, inner as columns
    if (hasOuter && hasInner) {
      return {
        rows: outerValuesWithIds,
        cols: innerValuesWithIds,
        is2D: true,
        rowDimId: outerDimId,
        colDimId: innerDimId,
        rowName: getDimensionName(outerDimId),
        colName: getDimensionName(innerDimId)
      };
    }
    
    // 1D case: use available dimension as rows, "Score" as column
    const availableValues = hasOuter ? outerValuesWithIds : innerValuesWithIds;
    const availableDimId = hasOuter ? outerDimId : innerDimId;
    
    return {
      rows: availableValues,
      cols: [{ id: 'score', value: 'Score' }],
      is2D: false,
      rowDimId: availableDimId,
      colDimId: undefined,
      rowName: getDimensionName(availableDimId),
      colName: 'Score'
    };
  }, [outerValuesWithIds, innerValuesWithIds, outerDimId, innerDimId, getDimensionName]);

  // Calculate average scores for each dimension combination or single dimension
  const dimensionScores = useMemo(() => {
    if (!statMarginals) return {};
    if (!outerValuesWithIds.length && !innerValuesWithIds.length) return {};
    
    // 2D case: both dimensions present
    if (outerValuesWithIds.length && innerValuesWithIds.length) {
      const scores: Record<string, Record<string, { score: number; n?: number; ci?: number }>> = {};
      outerValuesWithIds.forEach(({ id: outerId, value: outerValue }) => {
        scores[outerValue] = {};
        innerValuesWithIds.forEach(({ id: innerId, value: innerValue }) => {
          const key = `${innerDimId},${innerId}|${outerDimId},${outerId}`;
          const stats = statMarginals[key];
          scores[outerValue][innerValue] = getScoreFromStats(stats);
        });
      });
      return scores;
    }
    
    // 1D case: only one dimension present
    const availableValues = outerValuesWithIds.length ? outerValuesWithIds : innerValuesWithIds;
    const availableDimId = outerValuesWithIds.length ? outerDimId : innerDimId;
    
    const scores: Record<string, { score: number; n?: number; ci?: number }> = {};
    availableValues.forEach(({ id, value }) => {
      const key = `${availableDimId},${id}`;
      const stats = statMarginals[key];
      scores[value] = getScoreFromStats(stats);
    });
    
    return scores;
  }, [statMarginals, outerValuesWithIds, innerValuesWithIds, innerDimId, outerDimId]);

  // Add pagination state
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = PAGINATION_LIMIT; // Use constant instead of hardcoded value

  // Calculate pagination values
  const totalPages = Math.ceil(flatAgentRuns.length / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = Math.min(startIndex + itemsPerPage, flatAgentRuns.length);
  const currentPageItems = flatAgentRuns.slice(startIndex, endIndex);

  // Pagination controls
  const goToPage = (page: number) => {
    setCurrentPage(Math.max(1, Math.min(page, totalPages)));
  };

  // Helper function to create filters
  const createFilter = useCallback((dimId: string, value: string): PrimitiveFilter => ({
    type: 'primitive',
    key_path: dimensionsMap?.[dimId]?.metadata_key
      ? ['metadata', ...dimensionsMap[dimId].metadata_key.split('.')]
      : [],
    value,
    op: '==',
    id: crypto.randomUUID(),
    name: null,
  }), [dimensionsMap]);

  // If data isn't available, show a loading spinner
  if (!statMarginals || !idMarginals) {
    return (
      <Card className="h-full flex-1 p-3">
        <div className="flex-1 flex flex-col items-center justify-center space-y-2 h-full">
          <Loader2 className="h-5 w-5 animate-spin text-gray-500" />
        </div>
      </Card>
    );
  }

  return (
    <Card className="flex-1 p-3 flex flex-col min-h-0">
      {/* Header with organization dropdown - always visible */}
      <div className="flex justify-between items-center shrink-0">
        <div>
          <div className="text-sm font-semibold">
            Agent Run Viewer
          </div>
          <div className="text-xs">Compare agent performance across runs.</div>
        </div>
        {/* Place dimension selector in the header */}
        <DimensionSelector />
      </div>

      {/* Dimension scores table - always visible */}
      {tableData && (
        <div className="w-full border border-gray-200 rounded mb-4 shrink-0">
          <table className="w-full border-collapse text-xs">
            <thead>
              <tr>
                <th className="border border-gray-200 p-2 bg-gray-50 sticky left-0"></th>
                {tableData.cols.map(({ id: colId, value: colValue }) => (
                  <th
                    key={colId}
                    className="border border-gray-200 p-2 bg-gray-50 cursor-pointer hover:bg-indigo-100 transition-colors"
                    title={tableData.colDimId ? `Filter to ${tableData.colName}: ${colValue}` : undefined}
                    onClick={() => {
                      if (tableData.colDimId && dimensionsMap) {
                        const filter = createFilter(tableData.colDimId, colValue);
                        dispatch(addBaseFilter(filter));
                      }
                    }}
                  >
                    <span className="underline decoration-dotted underline-offset-2 cursor-pointer" style={{textDecorationStyle: 'dotted'}}>{colValue}</span>
                    {tableData.colDimId && <span className="absolute right-1 top-1 text-xs text-indigo-400" style={{fontSize: '10px'}}>&#128269;</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tableData.rows.map(({ id: rowId, value: rowValue }) => (
                <tr key={rowId}>
                  <td
                    className="border border-gray-200 p-2 bg-gray-50 font-medium sticky left-0 cursor-pointer hover:bg-indigo-100 transition-colors relative"
                    title={`Filter to ${tableData.rowName}: ${rowValue}`}
                    onClick={() => {
                      if (tableData.rowDimId && dimensionsMap) {
                        const filter = createFilter(tableData.rowDimId, rowValue);
                        dispatch(addBaseFilter(filter));
                      }
                    }}
                  >
                    <span className="underline decoration-dotted underline-offset-2 cursor-pointer" style={{textDecorationStyle: 'dotted'}}>{rowValue}</span>
                    <span className="absolute right-1 top-1 text-xs text-indigo-400" style={{fontSize: '10px'}}>&#128269;</span>
                  </td>
                  {tableData.cols.map(({ id: colId, value: colValue }) => {
                    // Get score data based on table type
                    let score: number | undefined;
                    let n: number | undefined;
                    let ci: number | undefined;
                    
                    if (tableData.is2D) {
                      // 2D case: use both dimensions
                      const row = dimensionScores[rowValue];
                      const cellData = typeof row === 'object' && row !== null ? (row as Record<string, { score: number; n?: number; ci?: number }>)[colValue] : undefined;
                      score = cellData?.score;
                      n = cellData?.n;
                      ci = cellData?.ci;
                    } else {
                      // 1D case: use single dimension
                      const cellData = dimensionScores[rowValue] as { score: number; n?: number; ci?: number } | undefined;
                      score = cellData?.score;
                      n = cellData?.n;
                      ci = cellData?.ci;
                    }
                    
                    return (
                      <td 
                        key={colId} 
                        className={`border border-gray-200 p-2 cursor-pointer hover:bg-indigo-100 transition-colors relative ${getScoreClass(score)}`}
                        title={getFilterTitle(tableData.rowName, rowValue, tableData.colName, colValue)}
                        onClick={() => {
                          if (tableData.rowDimId && dimensionsMap) {
                            if (tableData.is2D && tableData.colDimId) {
                              // 2D case: add both filters
                              const rowFilter = createFilter(tableData.rowDimId, rowValue);
                              const colFilter = createFilter(tableData.colDimId, colValue);
                              dispatch(addBaseFilters([rowFilter, colFilter]));
                            } else {
                              // 1D case: add single filter
                              const filter = createFilter(tableData.rowDimId, rowValue);
                              dispatch(addBaseFilter(filter));
                            }
                          }
                        }}
                      >
                        <span className="underline decoration-dotted underline-offset-2 cursor-pointer" style={{textDecorationStyle: 'dotted'}}>
                          {getScoreDisplay(score, ci)}
                        </span>
                        {n !== undefined && <span className="text-gray-500 ml-1">(n={n})</span>}
                        <span className="absolute right-1 top-1 text-xs text-indigo-400" style={{fontSize: '10px'}}>&#128269;</span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          {/* Show indicator when there are more than MAX_DIMENSION_VALUES rows */}
          {(totalOuterValues > MAX_DIMENSION_VALUES || totalInnerValues > MAX_DIMENSION_VALUES) && (
            <div className="px-2 py-1 bg-yellow-50 border-t border-yellow-200 text-xs text-yellow-700">
              {totalOuterValues > MAX_DIMENSION_VALUES && totalInnerValues > MAX_DIMENSION_VALUES ? (
                `Showing first ${MAX_DIMENSION_VALUES} of ${totalOuterValues} rows and first ${MAX_DIMENSION_VALUES} of ${totalInnerValues} columns`
              ) : totalOuterValues > MAX_DIMENSION_VALUES ? (
                `Showing first ${MAX_DIMENSION_VALUES} of ${totalOuterValues} rows`
              ) : (
                `Showing first ${MAX_DIMENSION_VALUES} of ${totalInnerValues} columns`
              )}
            </div>
          )}
        </div>
      )}

      {/* Content area: FLAT LIST of all agent runs - scrollable */}
      <div className="flex flex-col flex-1 min-h-0">
        {flatAgentRuns.length > 0 ? (
          <>
            <div className="flex-1 min-h-0 overflow-auto">
              {currentPageItems.map(({ agentRunId }) => {
                const attributes = curSearchQuery ? (attributeMap?.[agentRunId]?.[curSearchQuery]?.filter((attr: any) => attr.value !== null) || null) : null;
                return (
                  <div
                    key={agentRunId}
                    className="flex flex-col p-1 pb-[6px] border rounded text-xs bg-white/80 hover:bg-gray-50 mb-1"
                  >
                    <div
                      className="cursor-pointer"
                      onMouseDown={(e) =>
                        navToAgentRun(
                          e,
                          router,
                          window,
                          agentRunId,
                          undefined,
                          undefined,
                          frameGridId
                        )
                      }
                    >
                      <div className="flex justify-between items-center">
                        <span className="text-gray-600">
                          Agent Run <span className="font-mono">{agentRunId}</span>
                        </span>
                        <div className="flex gap-2">
                          <span
                            className="text-blue-600 font-medium hover:text-blue-700"
                            onMouseDown={(e) => {
                              navToAgentRun(
                                e,
                                router,
                                window,
                                agentRunId,
                                undefined,
                                undefined,
                                frameGridId,
                                curSearchQuery
                              );
                            }}
                          >
                            View
                          </span>
                        </div>
                      </div>
                      {/* Display metadata if available */}
                      {agentRunMetadata && agentRunMetadata[agentRunId] && (
                        <AgentRunMetadata agentRunId={agentRunId} />
                      )}
                    </div>
                    {/* Regex matches */}
                    <RegexSnippetsSection regexSnippets={regexSnippets?.[agentRunId]} />
                    {/* Attribute section if search query is active */}
                    {attributes && curSearchQuery && (
                      <AttributeSection
                        dataId={agentRunId}
                        curAttributeQuery={curSearchQuery}
                        attributes={attributes}
                      />
                    )}
                  </div>
                );
              })}
            </div>

            {/* Pagination Controls - always visible */}
            <div className="flex items-center justify-between px-2 py-2 border-t shrink-0">
              <div className="flex items-center gap-2">
                <button
                  onClick={() => goToPage(1)}
                  disabled={currentPage === 1}
                  className="p-1 rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <ChevronFirst className="h-4 w-4" />
                </button>
                <button
                  onClick={() => goToPage(currentPage - 1)}
                  disabled={currentPage === 1}
                  className="p-1 rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <span className="text-sm">
                  Page {currentPage} of {totalPages}
                </span>
                <button
                  onClick={() => goToPage(currentPage + 1)}
                  disabled={currentPage === totalPages}
                  className="p-1 rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
                <button
                  onClick={() => goToPage(totalPages)}
                  disabled={currentPage === totalPages}
                  className="p-1 rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <ChevronLast className="h-4 w-4" />
                </button>
              </div>
              <div className="text-sm text-gray-500">
                Showing {startIndex + 1}-{endIndex} of {flatAgentRuns.length} runs
              </div>
            </div>
          </>
        ) : (
          <div className="text-xs text-gray-500 min-h-[24px]">
            {loadingSearchQuery ? (
              <div className="flex items-center space-x-2">
                <span>Loading results...</span>
                <Loader2 className="h-3 w-3 animate-spin text-gray-500" />
              </div>
            ) : (
              'No results found'
            )}
          </div>
        )}
      </div>
    </Card>
  );
}
