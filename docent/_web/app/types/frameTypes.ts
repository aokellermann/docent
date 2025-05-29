import { Citation } from './experimentViewerTypes';

export interface Marginals {
  [dimId: string]: {
    [filterId: string]: Judgment[];
  };
}

export interface Judgment {
  id: string;
  agent_run_id: string;
  filter_id: string;
  search_query?: string | null;
  search_result_idx?: number | null;
  matches: boolean;
  reason?: string | null;
}

export interface FrameGrid {
  id: string;
  name: string | null;
  description: string | null;
  base_filter_id: string | null;
  sample_dim_id: string | null;
  experiment_dim_id: string | null;
  created_at: string;
}

export interface SearchResult {
  id: string;
  agent_run_id: string;
  search_query: string;
  search_result_idx?: number | null;
  value?: string | null;
}

export interface SearchResultWithCitations extends SearchResult {
  citations: Citation[] | null;
}

export type FilterLiteral =
  | 'primitive'
  | 'search_result_exists'
  | 'search_result_predicate'
  | 'complex'
  | 'agent_run_id';

export interface FrameFilter {
  id: string;
  name: string | null;
  type: FilterLiteral;
}

export interface AgentRunIdFilter extends FrameFilter {
  type: 'agent_run_id';
  value: string;
}

export interface PrimitiveFilter extends FrameFilter {
  type: 'primitive';
  key_path: string[];
  value: any;
  op: '==' | '!=' | '<' | '<=' | '>' | '>=' | '~*';
}

export type MetadataType = 'str' | 'int' | 'float' | 'bool';

export interface SearchResultExistsFilter extends FrameFilter {
  type: 'search_result_exists';
  search_query: string;
}

export interface SearchResultPredicateFilter extends FrameFilter {
  type: 'search_result_predicate';
  predicate: string;
  search_query: string;
  backend: string;
}

export interface ComplexFilter extends FrameFilter {
  type: 'complex';
  filters: FrameFilter[];
  op: 'and' | 'or';
}

export interface FrameDimension {
  id: string;
  name: string | null;
  bins: FrameFilter[] | null;
  search_query: string | null;
  metadata_key: string | null;
  maintain_mece: boolean | null;
  loading_clusters: boolean;
  loading_marginals: boolean;
}
