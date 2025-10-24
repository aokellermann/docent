export interface DqlForeignKey {
  column: string;
  target_table: string;
  target_column: string;
}

export interface DqlColumnSchema {
  name: string;
  data_type: string | null;
  nullable: boolean;
  is_primary_key: boolean;
  foreign_keys: DqlForeignKey[];
  alias_for?: string | null;
}

export interface DqlTableSchema {
  name: string;
  aliases?: string[];
  columns: DqlColumnSchema[];
}

export interface DqlSchemaResponse {
  tables: DqlTableSchema[];
}

export interface DqlColumnReference {
  table: string | null;
  column: string;
}

export interface DqlSelectedColumn {
  output_name: string;
  expression_sql: string;
  source_columns: DqlColumnReference[];
}

export interface DqlExecuteResponse {
  columns: string[];
  rows: unknown[][];
  truncated: boolean;
  row_count: number;
  execution_time_ms: number;
  requested_limit: number | null;
  applied_limit: number;
  selected_columns: DqlSelectedColumn[];
}

export interface DqlExecutePayload {
  dql: string;
}
