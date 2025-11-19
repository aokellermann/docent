const CONFIG_COLUMN_KEY = 'metadata.config';

export const isConfigColumn = (columnName: string): boolean =>
  columnName === CONFIG_COLUMN_KEY ||
  columnName.startsWith(`${CONFIG_COLUMN_KEY}.`);

/**
 * Sorts agent run column names so non-config metadata fields appear first,
 * config-specific metadata fields are grouped afterward, and `created_at`
 * remains the trailing column.
 */
export const compareAgentRunColumnNames = (a: string, b: string): number => {
  if (a === b) {
    return 0;
  }

  if (a === 'created_at') {
    return 1;
  }
  if (b === 'created_at') {
    return -1;
  }

  const aIsConfig = isConfigColumn(a);
  const bIsConfig = isConfigColumn(b);

  if (aIsConfig && !bIsConfig) {
    return 1;
  }
  if (!aIsConfig && bIsConfig) {
    return -1;
  }

  return a.localeCompare(b);
};
