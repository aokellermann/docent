/**
 * Shorten a UUID to its first segment (before the first hyphen).
 */
const shortenId = (id: string): string => {
  return id.split('-')[0] || id;
};

/**
 * Format a filter field label for display.
 *
 * Handles special field types:
 * - rubric.{uuid}.{path} → rubric:{short}.{path}
 * - label.{uuid}.{path} → label:{short}.{path}
 * - tag → tag
 * - metadata.{path} → metadata.{path} (unchanged)
 */
export const formatFilterFieldLabel = (fieldName: string): string => {
  const parts = fieldName.split('.');

  if (parts[0] === 'rubric' && parts.length >= 3) {
    const shortId = shortenId(parts[1]);
    return ['rubric', shortId, ...parts.slice(2)].join('.');
  }

  if (parts[0] === 'label' && parts.length >= 3) {
    const shortId = shortenId(parts[1]);
    return ['label', shortId, ...parts.slice(2)].join('.');
  }

  return fieldName;
};
