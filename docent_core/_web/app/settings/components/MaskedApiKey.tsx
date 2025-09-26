export function MaskedApiKey({ apiKey }: { apiKey: string }): React.ReactNode {
  return (
    <div className="font-mono text-sm bg-gray-100 dark:bg-gray-800 p-2 rounded">
      {apiKey}
    </div>
  );
}
