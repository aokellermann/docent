export const formatFilterFieldLabel = (fieldName: string): string => {
  if (!fieldName.startsWith('rubric.')) {
    return fieldName;
  }

  const parts = fieldName.split('.');
  if (parts.length < 3) {
    return fieldName;
  }

  const rubricId = parts[1];
  const shortId = rubricId.split('-')[0] || rubricId;
  return ['rubric', shortId, ...parts.slice(2)].join('.');
};
