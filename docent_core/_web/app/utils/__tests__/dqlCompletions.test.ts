import { describe, expect, it } from 'bun:test';

import {
  computeDqlSuggestions,
  type DqlCompletionSuggestion,
} from '@/app/utils/dqlCompletions';
import type { DqlSchemaResponse } from '@/app/types/dqlTypes';
import type { TranscriptMetadataField } from '@/app/types/experimentViewerTypes';

const schema: DqlSchemaResponse = {
  tables: [
    {
      name: 'agent_runs',
      aliases: ['ar'],
      columns: [
        {
          name: 'id',
          data_type: 'uuid',
          nullable: false,
          is_primary_key: true,
          foreign_keys: [],
          alias_for: null,
        },
        {
          name: 'collection_id',
          data_type: 'text',
          nullable: false,
          is_primary_key: false,
          foreign_keys: [],
          alias_for: null,
        },
        {
          name: 'metadata_json',
          data_type: 'jsonb',
          nullable: true,
          is_primary_key: false,
          foreign_keys: [],
          alias_for: null,
        },
      ],
    },
    {
      name: 'transcripts',
      aliases: ['t'],
      columns: [
        {
          name: 'id',
          data_type: 'uuid',
          nullable: false,
          is_primary_key: true,
          foreign_keys: [],
          alias_for: null,
        },
      ],
    },
  ],
};

const metadataFields: TranscriptMetadataField[] = [
  { name: 'metadata.foo', type: 'str' },
  { name: 'metadata.stats.score', type: 'float' },
  { name: 'metadata.stats.detail', type: 'str' },
];

const collectLabels = (suggestions: DqlCompletionSuggestion[]): string[] =>
  suggestions.map((suggestion) => suggestion.label);

const allTableLabels: string[] = schema.tables.flatMap((table) => [
  table.name,
  ...(table.aliases ?? []),
]);

const tableColumnLabelMap: Map<string, string[]> = new Map(
  schema.tables.map((table) => [
    table.name,
    table.columns.map((column) => `${table.name}.${column.name}`),
  ])
);

const allColumnLabels: string[] = Array.from(
  tableColumnLabelMap.values()
).flat();

const aliasColumnsFor = (tableName: string, alias: string) =>
  (tableColumnLabelMap.get(tableName) ?? []).map((label) =>
    label.replace(`${tableName}.`, `${alias}.`)
  );

const expectLabelsContainAll = (labels: string[], expected: string[]) => {
  expected.forEach((value) => expect(labels).toContain(value));
};

const expectLabelsExcludeAll = (labels: string[], forbidden: string[]) => {
  forbidden.forEach((value) => expect(labels).not.toContain(value));
};

const runCompletion = (doc: string, position?: number) => {
  const offset = position ?? doc.length;
  return computeDqlSuggestions(doc, offset, schema, metadataFields);
};

const findMetadataSuggestion = (
  result: ReturnType<typeof runCompletion>,
  segment: string
) =>
  result.find(
    (suggestion) =>
      suggestion.kind === 'metadata' && suggestion.label === `'${segment}'`
  );

describe('computeDqlSuggestions', () => {
  const labelsFor = (doc: string, position?: number) =>
    collectLabels(runCompletion(doc, position));

  it('suggests SELECT keyword for empty input', () => {
    expect(labelsFor('')).toContain('SELECT');
  });

  it('suggests WHERE after a FROM clause when keyword is partially typed', () => {
    const doc = 'SELECT collection_id FROM agent_runs wh';
    expect(labelsFor(doc)).toContain('WHERE');
  });

  it('does not suggest WHERE before a FROM clause has been written', () => {
    const doc = 'SELECT agent_runs.collection_id w';
    expect(labelsFor(doc)).not.toContain('WHERE');
  });

  it('suggests columns when accessing a table directly without aliases', () => {
    const doc = 'SELECT agent_runs.';
    const labels = labelsFor(doc);
    expect(labels).toContain('agent_runs.collection_id');
    expect(labels).toContain('agent_runs.metadata_json');
  });

  it('suggests tables and columns after typing SELECT', () => {
    const labels = labelsFor('SELECT ');
    expectLabelsContainAll(labels, allTableLabels);
    expectLabelsContainAll(labels, allColumnLabels);
  });

  it('suggests all tables and aliases after typing SELECT', () => {
    const labels = labelsFor('SELECT ');
    expectLabelsContainAll(labels, allTableLabels);
  });

  it('suggests all table-scoped columns after typing SELECT', () => {
    const labels = labelsFor('SELECT ');
    expectLabelsContainAll(labels, allColumnLabels);
  });

  it('suggests additional columns after a comma in the select list', () => {
    const labels = labelsFor('SELECT agent_runs.id, ');
    expect(labels).toContain('agent_runs.collection_id');
    expect(labels).toContain('transcripts.id');
  });

  it('suggests table names right after a FROM keyword', () => {
    const labels = labelsFor('SELECT id FROM ');
    expect(labels).toContain('agent_runs');
    expect(labels).toContain('transcripts');
  });

  it('suggests tables but not columns immediately after FROM', () => {
    const labels = labelsFor('SELECT agent_runs.id FROM ');
    expectLabelsContainAll(labels, allTableLabels);
    expectLabelsExcludeAll(labels, allColumnLabels);
  });

  it('suggests keywords but not columns after specifying a FROM table', () => {
    const labels = labelsFor('SELECT agent_runs.id FROM agent_runs ');
    expect(labels).toContain('WHERE');
    expectLabelsExcludeAll(labels, allColumnLabels);
  });

  it('suggests tables but not columns immediately after JOIN', () => {
    const labels = labelsFor('SELECT agent_runs.id FROM agent_runs JOIN ');
    expectLabelsContainAll(labels, allTableLabels);
    expectLabelsExcludeAll(labels, allColumnLabels);
  });

  it('orders matching table before its columns when typing prefix', () => {
    const firstTableLabel = [...allTableLabels].sort((a, b) =>
      a.localeCompare(b)
    )[0];
    const prefix = firstTableLabel.slice(0, 2);
    const result = runCompletion(`SELECT ${prefix}`);
    const labels = result.map((suggestion) => suggestion.label);
    expect(labels[0]).toBe(firstTableLabel);
    const tableName = firstTableLabel.includes('.')
      ? firstTableLabel.split('.')[0]
      : firstTableLabel;
    const agentColumns =
      tableColumnLabelMap.get(tableName) ??
      tableColumnLabelMap.get('agent_runs') ??
      [];
    expectLabelsContainAll(labels, agentColumns);
    agentColumns.forEach((columnLabel) => {
      const index = labels.indexOf(columnLabel);
      expect(index).toBeGreaterThan(0);
    });
  });

  it('inserts fully-qualified column names for table-prefixed suggestions', () => {
    const firstTableLabel = [...allTableLabels].sort((a, b) =>
      a.localeCompare(b)
    )[0];
    const firstColumnLabel = [...allColumnLabels]
      .filter((label) => label.startsWith(firstTableLabel))
      .sort((a, b) => a.localeCompare(b))[0];
    const query = `SELECT ${firstTableLabel.slice(0, 2)}`;
    const result = runCompletion(query);
    const suggestion = result.find((item) => item.label === firstColumnLabel);
    expect(suggestion).toBeDefined();
    expect(suggestion?.insertText).toBe(firstColumnLabel);
  });

  it('inserts unqualified column names when qualifier already present', () => {
    const firstTableLabel = [...allTableLabels].sort((a, b) =>
      a.localeCompare(b)
    )[0];
    const firstColumnLabel = [...allColumnLabels]
      .filter((label) => label.startsWith(firstTableLabel))
      .sort((a, b) => a.localeCompare(b))[0];
    const query = `SELECT ${firstTableLabel}.`;
    const position = query.length;
    const result = runCompletion(query, position);
    const suggestion = result.find((item) => item.label === firstColumnLabel);
    expect(suggestion).toBeDefined();
    expect(suggestion?.insertText).toBe(firstColumnLabel.split('.').pop());
  });

  it('prefers tables before columns inside ON clause', () => {
    const result = runCompletion(
      'SELECT agent_runs.id FROM agent_runs LEFT JOIN judge_results ON '
    );
    expect(result[0]?.kind).toBe('table');
    expect(result[1]?.kind).toBe('table');
    const labels = result.map((suggestion) => suggestion.label);
    expect(labels.some((label) => label.startsWith('left.'))).toBe(false);
    expect(labels.some((label) => label.startsWith('on.'))).toBe(false);
  });

  it('prefers tables before columns inside ON clause parentheses', () => {
    const result = runCompletion(
      'SELECT agent_runs.id FROM agent_runs LEFT JOIN judge_results ON ('
    );
    expect(result[0]?.kind).toBe('table');
    expect(result[1]?.kind).toBe('table');
  });

  it('prefers tables before columns after ON comparison', () => {
    const result = runCompletion(
      'SELECT agent_runs.id FROM agent_runs LEFT JOIN judge_results ON (agent_runs.id = '
    );
    expect(result[0]?.kind).toBe('table');
    expect(result[1]?.kind).toBe('table');
  });

  it('prefers tables before columns inside FROM subqueries', () => {
    const result = runCompletion('SELECT agent_runs.id FROM (');
    expect(result[0]?.kind).toBe('table');
    expect(result[1]?.kind).toBe('table');
  });

  it('suggests ON keyword after a JOIN', () => {
    const labels = labelsFor('SELECT id FROM agent_runs JOIN ');
    expect(labels).toContain('ON');
  });

  it('suggests columns from both sides within an ON clause', () => {
    const labels = labelsFor(
      'SELECT id FROM agent_runs JOIN transcripts t ON '
    );
    expect(labels).toContain('agent_runs.id');
    expect(labels).toContain('transcripts.id');
  });

  it('suggests table and column names inside a subquery', () => {
    const labels = labelsFor('SELECT id FROM agent_runs WHERE EXISTS (SELECT ');
    expect(labels).toContain('agent_runs.id');
    expect(labels).toContain('transcripts');
  });

  it('suggests alias columns inside a subquery predicate', () => {
    const doc =
      'SELECT id FROM agent_runs WHERE EXISTS (SELECT 1 FROM transcripts t WHERE t.';
    const position = doc.length;
    const labels = labelsFor(doc, position);
    expect(labels).toContain('t.id');
  });

  it('suggests metadata json segments for aliases with metadata access', () => {
    const doc = 'SELECT ar.metadata_json->';
    const position = doc.indexOf('->') + 2;
    const labels = labelsFor(doc, position);
    expect(labels).toContain("'foo'");
    expect(labels).toContain("'stats'");
  });

  it('filters metadata suggestions to matching prefixes', () => {
    const doc = "SELECT ar.metadata_json->'s";
    const position = doc.indexOf("'s") + 2;
    const labels = labelsFor(doc, position);
    expect(labels).toContain("'stats'");
    expect(labels).not.toContain("'foo'");
  });

  it('does not duplicate quotes when completing metadata segments after an opening quote', () => {
    const doc = "SELECT agent_runs.metadata_json->'";
    const result = runCompletion(doc);
    const metadataSuggestion = findMetadataSuggestion(result, 'foo');
    expect(metadataSuggestion?.insertText).toBe("foo'");
    expect(metadataSuggestion?.replaceBefore).toBeUndefined();
  });

  it('includes opening quotes when completing metadata segments without a typed quote', () => {
    const doc = 'SELECT agent_runs.metadata_json->';
    const result = runCompletion(doc);
    const metadataSuggestion = findMetadataSuggestion(result, 'foo');
    expect(metadataSuggestion?.insertText).toBe("'foo'");
  });

  it('omits both quotes when completing metadata segments already wrapped in quotes', () => {
    const doc = "SELECT agent_runs.metadata_json->''";
    const position = doc.indexOf("''") + 1;
    const result = runCompletion(doc, position);
    const metadataSuggestion = findMetadataSuggestion(result, 'foo');
    expect(metadataSuggestion?.insertText).toBe('foo');
    expect(metadataSuggestion?.replaceBefore).toBeUndefined();
  });

  it('fills empty metadata segment shells positioned after both quotes', () => {
    const doc = "SELECT agent_runs.metadata_json->''";
    const result = runCompletion(doc);
    const metadataSuggestion = findMetadataSuggestion(result, 'foo');
    expect(metadataSuggestion?.insertText).toBe("foo'");
    expect(metadataSuggestion?.replaceBefore).toBe(1);
  });

  it('suggests child metadata segments after selecting a parent object', () => {
    const doc = "SELECT ar.metadata_json->'stats'->";
    const position = doc.indexOf('->', doc.indexOf("'stats'")) + 2;
    const labels = labelsFor(doc, position);
    expect(labels).toContain("'score'");
    expect(labels).toContain("'detail'");
    expect(labels).not.toContain("'foo'");
  });

  it('does not offer metadata completions for tables without metadata', () => {
    const doc = 'SELECT transcripts.metadata_json->';
    const position = doc.indexOf('->') + 2;
    const result = runCompletion(doc, position);
    const metadataSuggestions = result.filter(
      (suggestion) => suggestion.kind === 'metadata'
    );
    expect(metadataSuggestions.length).toBe(0);
  });

  describe('keyword suggestion coverage', () => {
    const whereKeywordCases: Array<{ name: string; expected: string }> = [
      { name: 'includes AND in WHERE suggestions', expected: 'AND' },
      { name: 'includes OR in WHERE suggestions', expected: 'OR' },
      { name: 'includes NOT in WHERE suggestions', expected: 'NOT' },
      { name: 'includes BETWEEN in WHERE suggestions', expected: 'BETWEEN' },
      { name: 'includes IN in WHERE suggestions', expected: 'IN' },
      { name: 'includes LIKE in WHERE suggestions', expected: 'LIKE' },
      { name: 'includes ILIKE in WHERE suggestions', expected: 'ILIKE' },
      { name: 'includes IS NULL in WHERE suggestions', expected: 'IS NULL' },
      {
        name: 'includes IS NOT NULL in WHERE suggestions',
        expected: 'IS NOT NULL',
      },
    ];

    whereKeywordCases.forEach(({ name, expected }) => {
      it(name, () => {
        const labels = labelsFor('SELECT id FROM agent_runs WHERE ');
        expect(labels).toContain(expected);
      });
    });

    it('includes EXISTS in WHERE suggestions', () => {
      const labels = labelsFor('SELECT id FROM agent_runs WHERE ');
      expect(labels).toContain('EXISTS');
    });

    const fromKeywordCases: Array<{
      name: string;
      expected: string;
      doc: string;
    }> = [
      {
        name: 'includes JOIN after FROM clause',
        expected: 'JOIN',
        doc: 'SELECT id FROM agent_runs ',
      },
      {
        name: 'includes LEFT JOIN after FROM clause',
        expected: 'LEFT JOIN',
        doc: 'SELECT id FROM agent_runs ',
      },
      {
        name: 'includes RIGHT JOIN after FROM clause',
        expected: 'RIGHT JOIN',
        doc: 'SELECT id FROM agent_runs ',
      },
      {
        name: 'includes OUTER JOIN after FROM clause',
        expected: 'OUTER JOIN',
        doc: 'SELECT id FROM agent_runs ',
      },
      {
        name: 'includes INNER JOIN after FROM clause',
        expected: 'INNER JOIN',
        doc: 'SELECT id FROM agent_runs ',
      },
      {
        name: 'includes WHERE after FROM clause',
        expected: 'WHERE',
        doc: 'SELECT id FROM agent_runs ',
      },
      {
        name: 'includes LIMIT after FROM clause',
        expected: 'LIMIT',
        doc: 'SELECT id FROM agent_runs ',
      },
      {
        name: 'includes ORDER BY after FROM clause',
        expected: 'ORDER BY',
        doc: 'SELECT id FROM agent_runs ',
      },
    ];

    fromKeywordCases.forEach(({ name, expected, doc }) => {
      it(name, () => {
        const labels = labelsFor(doc);
        expect(labels).toContain(expected);
      });
    });

    it('includes OFFSET after LIMIT clause', () => {
      const labels = labelsFor('SELECT id FROM agent_runs LIMIT 10 ');
      expect(labels).toContain('OFFSET');
    });

    it('includes ON after a JOIN keyword', () => {
      const labels = labelsFor('SELECT id FROM agent_runs JOIN transcripts ');
      expect(labels).toContain('ON');
    });

    const orderByKeywordCases: Array<{
      name: string;
      expected: string;
      doc: string;
    }> = [
      {
        name: 'includes ASC after ORDER BY',
        expected: 'ASC',
        doc: 'SELECT id FROM agent_runs ORDER BY ',
      },
      {
        name: 'includes DESC after ORDER BY',
        expected: 'DESC',
        doc: 'SELECT id FROM agent_runs ORDER BY ',
      },
      {
        name: 'includes NULLS FIRST after ORDER BY',
        expected: 'NULLS FIRST',
        doc: 'SELECT id FROM agent_runs ORDER BY ',
      },
      {
        name: 'includes NULLS LAST after ORDER BY',
        expected: 'NULLS LAST',
        doc: 'SELECT id FROM agent_runs ORDER BY ',
      },
    ];

    orderByKeywordCases.forEach(({ name, expected, doc }) => {
      it(name, () => {
        const labels = labelsFor(doc);
        expect(labels).toContain(expected);
      });
    });

    it('includes GROUP BY after SELECT with aggregate', () => {
      const labels = labelsFor('SELECT id, COUNT(*) FROM agent_runs ');
      expect(labels).toContain('GROUP BY');
    });

    const havingKeywordCases: Array<{ name: string; expected: string }> = [
      { name: 'includes AND in HAVING suggestions', expected: 'AND' },
      { name: 'includes OR in HAVING suggestions', expected: 'OR' },
      { name: 'includes NOT in HAVING suggestions', expected: 'NOT' },
      { name: 'includes BETWEEN in HAVING suggestions', expected: 'BETWEEN' },
      { name: 'includes IN in HAVING suggestions', expected: 'IN' },
    ];

    havingKeywordCases.forEach(({ name, expected }) => {
      it(name, () => {
        const labels = labelsFor(
          'SELECT agent_runs.collection_id, COUNT(*) FROM agent_runs GROUP BY agent_runs.collection_id HAVING '
        );
        expect(labels).toContain(expected);
      });
    });

    const caseKeywordCases: Array<{
      name: string;
      doc: string;
      expected: string;
    }> = [
      {
        name: 'includes WHEN after CASE',
        doc: 'SELECT CASE ',
        expected: 'WHEN',
      },
      {
        name: 'includes THEN after WHEN',
        doc: 'SELECT CASE WHEN ',
        expected: 'THEN',
      },
      {
        name: 'includes ELSE after THEN expression',
        doc: 'SELECT CASE WHEN agent_runs.id IS NOT NULL THEN agent_runs.id ',
        expected: 'ELSE',
      },
      {
        name: 'includes END after ELSE expression',
        doc: 'SELECT CASE WHEN agent_runs.id IS NOT NULL THEN agent_runs.id ELSE agent_runs.collection_id ',
        expected: 'END',
      },
      {
        name: 'includes AS after CASE expression completes',
        doc: 'SELECT CASE WHEN agent_runs.id IS NOT NULL THEN agent_runs.id ELSE agent_runs.collection_id END ',
        expected: 'AS',
      },
    ];

    caseKeywordCases.forEach(({ name, doc, expected }) => {
      it(name, () => {
        const labels = labelsFor(doc);
        expect(labels).toContain(expected);
      });
    });

    const selectKeywordCases: Array<{
      name: string;
      doc: string;
      expected: string;
    }> = [
      {
        name: 'includes DISTINCT after SELECT',
        doc: 'SELECT ',
        expected: 'DISTINCT',
      },
      {
        name: 'includes DISTINCT after typing prefix',
        doc: 'SELECT D',
        expected: 'DISTINCT',
      },
    ];

    selectKeywordCases.forEach(({ name, doc, expected }) => {
      it(name, () => {
        const labels = labelsFor(doc);
        expect(labels).toContain(expected);
      });
    });
  });

  describe('column and metadata suggestion coverage', () => {
    const columnCases: Array<{
      name: string;
      doc: string;
      expected: string;
      position?: number;
    }> = [
      {
        name: 'suggests columns for fully qualified table',
        doc: 'SELECT agent_runs.',
        expected: 'agent_runs.id',
      },
      {
        name: 'suggests columns for schema alias',
        doc: 'SELECT ar.',
        expected: 'ar.collection_id',
      },
      {
        name: 'suggests columns for transcripts table',
        doc: 'SELECT transcripts.',
        expected: 'transcripts.id',
      },
      {
        name: 'suggests columns for transcripts alias',
        doc: 'SELECT t.',
        expected: 't.id',
      },
      {
        name: 'suggests columns using table qualifier inside WHERE',
        doc: 'SELECT agent_runs.id FROM agent_runs WHERE agent_runs.',
        expected: 'agent_runs.collection_id',
      },
      {
        name: 'suggests columns using alias qualifier inside WHERE',
        doc: 'SELECT agent_runs.id FROM agent_runs ar WHERE ar.',
        expected: 'ar.metadata_json',
      },
      {
        name: 'suggests alias columns inside ON clause for agent_runs',
        doc: 'SELECT id FROM agent_runs ar JOIN transcripts t ON ar.',
        expected: 'ar.id',
      },
      {
        name: 'suggests alias columns inside ON clause for transcripts',
        doc: 'SELECT id FROM agent_runs ar JOIN transcripts t ON t.',
        expected: 't.id',
      },
      {
        name: 'suggests alias columns inside nested subquery',
        doc: 'SELECT id FROM agent_runs WHERE EXISTS (SELECT 1 FROM agent_runs ar2 WHERE ar2.',
        expected: 'ar2.id',
      },
      {
        name: 'suggests table columns inside nested subquery',
        doc: 'SELECT id FROM agent_runs WHERE EXISTS (SELECT 1 FROM transcripts WHERE transcripts.',
        expected: 'transcripts.id',
      },
      {
        name: 'suggests alias columns after comparison in subquery',
        doc: 'SELECT id FROM agent_runs WHERE EXISTS (SELECT 1 FROM agent_runs ar2 WHERE ar2.id = agent_runs.id AND ar2.',
        expected: 'ar2.collection_id',
      },
      {
        name: 'suggests metadata segments for table qualifier',
        doc: 'SELECT agent_runs.metadata_json->',
        expected: "'foo'",
      },
      {
        name: 'suggests metadata segments for alias qualifier',
        doc: 'SELECT ar.metadata_json->',
        expected: "'stats'",
      },
      {
        name: 'suggests nested metadata segments for table qualifier',
        doc: "SELECT agent_runs.metadata_json->'stats'->",
        expected: "'detail'",
      },
      {
        name: 'suggests nested metadata segments for alias qualifier',
        doc: "SELECT ar.metadata_json->'stats'->",
        expected: "'score'",
      },
      {
        name: 'suggests nested metadata segments filtered by prefix for table qualifier',
        doc: "SELECT agent_runs.metadata_json->'stats'->'s",
        expected: "'score'",
      },
      {
        name: 'suggests nested metadata segments filtered by prefix for alias qualifier',
        doc: "SELECT ar.metadata_json->'stats'->'d",
        expected: "'detail'",
      },
      {
        name: 'suggests top-level metadata segments filtered by prefix',
        doc: "SELECT agent_runs.metadata_json->'f",
        expected: "'foo'",
      },
      {
        name: 'suggests columns when qualifier typed partially in WHERE clause',
        doc: 'SELECT agent_runs.id FROM agent_runs WHERE agen',
        expected: 'agent_runs.id',
      },
      {
        name: 'suggests transcripts columns after comma in select list',
        doc: 'SELECT agent_runs.id, transcripts.',
        expected: 'transcripts.id',
      },
      {
        name: 'suggests alias columns after comma in select list',
        doc: 'SELECT agent_runs.id, t.',
        expected: 't.id',
      },
      {
        name: 'suggests alias columns inside ORDER BY clause',
        doc: 'SELECT agent_runs.id FROM agent_runs ar ORDER BY ar.',
        expected: 'ar.collection_id',
      },
      {
        name: 'suggests alias columns inside GROUP BY clause',
        doc: 'SELECT ar.id, COUNT(*) FROM agent_runs ar GROUP BY ar.',
        expected: 'ar.id',
      },
      {
        name: 'suggests alias columns inside HAVING clause',
        doc: 'SELECT ar.id, COUNT(*) FROM agent_runs ar GROUP BY ar.id HAVING ar.',
        expected: 'ar.id',
      },
    ];

    columnCases.forEach(({ name, doc, expected, position }) => {
      it(name, () => {
        const labels = labelsFor(doc, position);
        expect(labels).toContain(expected);
      });
    });

    it('suggests every column for each base table qualifier', () => {
      schema.tables.forEach((table) => {
        const columnLabels = tableColumnLabelMap.get(table.name) ?? [];
        const labels = labelsFor(`SELECT ${table.name}.`);
        expectLabelsContainAll(labels, columnLabels);
      });
    });
  });

  describe('subquery suggestion coverage', () => {
    const subqueryCases: Array<{
      name: string;
      doc: string;
      expected: string;
      position?: number;
    }> = [
      {
        name: 'suggests table names at start of EXISTS subquery',
        doc: 'SELECT id FROM agent_runs WHERE EXISTS (SELECT ',
        expected: 'agent_runs',
      },
      {
        name: 'suggests columns for table in EXISTS subquery select list',
        doc: 'SELECT id FROM agent_runs WHERE EXISTS (SELECT agent_runs.',
        expected: 'agent_runs.id',
      },
      {
        name: 'suggests alias columns inside EXISTS subquery where clause',
        doc: 'SELECT id FROM agent_runs WHERE EXISTS (SELECT 1 FROM agent_runs ar2 WHERE ar2.',
        expected: 'ar2.id',
      },
      {
        name: 'suggests alias columns after predicate inside EXISTS subquery',
        doc: 'SELECT id FROM agent_runs WHERE EXISTS (SELECT 1 FROM agent_runs ar2 WHERE ar2.id = agent_runs.id OR ar2.',
        expected: 'ar2.metadata_json',
      },
      {
        name: 'suggests WHERE keywords inside nested subquery',
        doc: 'SELECT id FROM agent_runs WHERE EXISTS (SELECT 1 FROM agent_runs ar2 WHERE ',
        expected: 'AND',
      },
      {
        name: 'suggests OR keyword inside nested subquery predicate',
        doc: 'SELECT id FROM agent_runs WHERE EXISTS (SELECT 1 FROM agent_runs ar2 WHERE ar2.id = agent_runs.id OR ',
        expected: 'OR',
      },
      {
        name: 'suggests transcripts columns inside subquery without alias',
        doc: 'SELECT id FROM agent_runs WHERE EXISTS (SELECT 1 FROM transcripts WHERE transcripts.',
        expected: 'transcripts.id',
      },
      {
        name: 'suggests keywords after transcripts subquery WHERE',
        doc: 'SELECT id FROM agent_runs WHERE EXISTS (SELECT 1 FROM transcripts WHERE ',
        expected: 'AND',
      },
      {
        name: 'suggests transcripts alias columns inside subquery',
        doc: 'SELECT id FROM agent_runs WHERE EXISTS (SELECT 1 FROM transcripts t WHERE t.',
        expected: 't.id',
      },
      {
        name: 'suggests keywords inside transcripts alias subquery where clause',
        doc: 'SELECT id FROM agent_runs WHERE EXISTS (SELECT 1 FROM transcripts t WHERE ',
        expected: 'AND',
      },
      {
        name: 'suggests columns inside IN subquery select list',
        doc: 'SELECT id FROM agent_runs WHERE agent_runs.id IN (SELECT ',
        expected: 'agent_runs.id',
      },
      {
        name: 'suggests transcripts columns inside IN subquery',
        doc: 'SELECT id FROM agent_runs WHERE agent_runs.id IN (SELECT transcripts.',
        expected: 'transcripts.id',
      },
      {
        name: 'suggests keywords inside IN subquery WHERE clause',
        doc: 'SELECT id FROM agent_runs WHERE agent_runs.id IN (SELECT 1 FROM transcripts WHERE ',
        expected: 'OR',
      },
      {
        name: 'suggests alias columns inside IN subquery predicate',
        doc: 'SELECT id FROM agent_runs WHERE agent_runs.id IN (SELECT 1 FROM transcripts t WHERE t.id = agent_runs.id AND t.',
        expected: 't.id',
      },
      {
        name: 'suggests ordering keywords inside nested subquery',
        doc: 'SELECT id FROM agent_runs WHERE EXISTS (SELECT 1 FROM agent_runs ar2 WHERE ar2.collection_id = agent_runs.collection_id ORDER BY ',
        expected: 'ASC',
      },
    ];

    subqueryCases.forEach(({ name, doc, expected, position }) => {
      it(name, () => {
        const labels = labelsFor(doc, position);
        expect(labels).toContain(expected);
      });
    });
  });

  describe('nested subquery suggestion coverage', () => {
    it('suggests alias columns inside subquery nested within another subquery', () => {
      const doc =
        'SELECT id FROM agent_runs WHERE EXISTS (SELECT 1 FROM transcripts t WHERE EXISTS (SELECT 1 FROM agent_runs ar2 WHERE ar2.';
      const labels = labelsFor(doc);
      expect(labels).toContain('ar2.id');
      expect(labels).toContain('ar2.collection_id');
    });

    it('suggests boolean operators inside deeply nested subquery predicates', () => {
      const doc =
        'SELECT id FROM agent_runs WHERE EXISTS (SELECT 1 FROM transcripts t WHERE EXISTS (SELECT 1 FROM agent_runs ar2 WHERE ';
      const labels = labelsFor(doc);
      expectLabelsContainAll(labels, ['AND', 'OR']);
    });

    it('suggests outer table columns inside nested subquery comparison', () => {
      const doc =
        'SELECT id FROM agent_runs WHERE EXISTS (SELECT 1 FROM transcripts t WHERE EXISTS (SELECT 1 FROM agent_runs ar2 WHERE ar2.id = t.id AND agent_runs.';
      const labels = labelsFor(doc);
      expectLabelsContainAll(
        labels,
        tableColumnLabelMap.get('agent_runs') ?? []
      );
    });

    it('omits DML statements within deeply nested subquery contexts', () => {
      const doc =
        'SELECT id FROM agent_runs WHERE EXISTS (SELECT 1 FROM transcripts t WHERE EXISTS (SELECT 1 FROM agent_runs ar2 WHERE ';
      const labels = labelsFor(doc);
      expectLabelsExcludeAll(labels, ['DELETE', 'UPDATE', 'INSERT']);
    });
  });

  describe('negative suggestion scenarios', () => {
    const negativeCases: Array<{
      name: string;
      doc: string;
      forbidden: string[];
      position?: number;
      expectEmpty?: boolean;
    }> = [
      {
        name: 'returns no suggestions for unknown qualifier',
        doc: 'SELECT foo.',
        forbidden: [],
        expectEmpty: true,
      },
      {
        name: 'filters JOIN when typing SELECT s prefix',
        doc: 'SELECT s',
        forbidden: ['JOIN'],
      },
      {
        name: 'filters JOIN when typing WHERE prefix',
        doc: 'SELECT agent_runs.id FROM agent_runs WHERE i',
        forbidden: ['JOIN'],
      },
      {
        name: 'filters JOIN when typing ORDER BY prefix',
        doc: 'SELECT agent_runs.id FROM agent_runs ORDER BY a',
        forbidden: ['JOIN'],
      },
      {
        name: 'filters JOIN when typing GROUP BY prefix',
        doc: 'SELECT agent_runs.id FROM agent_runs GROUP BY g',
        forbidden: ['JOIN'],
      },
      {
        name: 'omits metadata suggestions when prefix mismatched for table qualifier',
        doc: "SELECT agent_runs.metadata_json->'z",
        forbidden: ["'foo'", "'stats'"],
        expectEmpty: true,
      },
      {
        name: 'does not suggest transcripts columns for agent_runs qualifier',
        doc: 'SELECT agent_runs.id FROM agent_runs WHERE agent_runs.',
        forbidden: ['transcripts.id', 't.id'],
      },
      {
        name: 'does not suggest metadata for tables without metadata columns',
        doc: 'SELECT transcripts.metadata_json->',
        forbidden: ["'foo'", "'stats'"],
      },
      {
        name: 'prefix filtering excludes alias columns that do not match inside WHERE clause',
        doc: 'SELECT agent_runs.id FROM agent_runs ar WHERE ar.m',
        forbidden: ['ar.id'],
      },
      {
        name: 'does not suggest HAVING without GROUP BY clause',
        doc: 'SELECT agent_runs.id FROM agent_runs ',
        forbidden: ['HAVING'],
      },
      {
        name: 'does not suggest columns for unknown qualifier within WHERE clause',
        doc: 'SELECT agent_runs.id FROM agent_runs WHERE foo.',
        forbidden: [],
        expectEmpty: true,
      },
      {
        name: 'prefix filtering excludes alias columns that do not match inside ORDER BY clause',
        doc: 'SELECT agent_runs.id FROM agent_runs ar ORDER BY ar.m',
        forbidden: ['ar.id'],
      },
      {
        name: 'metadata nested prefix filters out unmatched segments',
        doc: "SELECT agent_runs.metadata_json->'stats'->'x",
        forbidden: ["'score'", "'detail'"],
      },
      {
        name: 'does not suggest WHERE keywords inside metadata chain',
        doc: "SELECT agent_runs.metadata_json->'stats'->",
        forbidden: ['WHERE'],
      },
      {
        name: 'prefix filtering excludes JOIN within CASE expression',
        doc: 'SELECT CASE W',
        forbidden: ['JOIN'],
      },
      {
        name: 'does not surface write statements in SELECT context',
        doc: 'SELECT ',
        forbidden: ['DELETE', 'UPDATE', 'INSERT'],
      },
      {
        name: 'does not suggest WHERE before FROM clause',
        doc: 'SELECT agent_runs.collection_id w',
        forbidden: ['WHERE'],
      },
      {
        name: 'does not suggest metadata segments without metadata path',
        doc: 'SELECT agent_runs.id FROM agent_runs WHERE ',
        forbidden: ["'foo'"],
      },
      {
        name: 'prefix filtering excludes ORDER BY when typing WHERE s prefix',
        doc: 'SELECT agent_runs.id FROM agent_runs WHERE s',
        forbidden: ['ORDER BY'],
      },
      {
        name: 'does not suggest WHERE inside SELECT list metadata access',
        doc: "SELECT agent_runs.metadata_json->'stats'->",
        forbidden: ['WHERE'],
      },
    ];

    negativeCases.forEach(({ name, doc, forbidden, position, expectEmpty }) => {
      it(name, () => {
        const labels = labelsFor(doc, position);
        if (expectEmpty) {
          expect(labels.length).toBe(0);
          return;
        }
        expectLabelsExcludeAll(labels, forbidden);
      });
    });
  });

  describe('suggestion ranking', () => {
    const sortedTables = [...allTableLabels].sort((a, b) => a.localeCompare(b));
    const sortedColumns = [...allColumnLabels].sort((a, b) =>
      a.localeCompare(b)
    );
    const primaryTable = schema.tables[0];
    const primaryAlias = primaryTable.aliases?.[0] ?? null;
    const primaryColumns = tableColumnLabelMap.get(primaryTable.name) ?? [];
    const primaryAliasColumns = primaryAlias
      ? aliasColumnsFor(primaryTable.name, primaryAlias)
      : [];
    const secondaryTable = schema.tables[1];
    const secondaryAlias = secondaryTable.aliases?.[0] ?? null;
    const secondaryColumns = tableColumnLabelMap.get(secondaryTable.name) ?? [];
    const secondaryAliasColumns = secondaryAlias
      ? aliasColumnsFor(secondaryTable.name, secondaryAlias)
      : [];

    it('ranks columns ahead of tables for blank select', () => {
      const result = runCompletion('SELECT ');
      expect(result[0]?.label).toBe(sortedColumns[0]);
    });

    it('ranks first table for shared prefix', () => {
      const firstTable = sortedTables[0];
      const prefix = firstTable.slice(0, Math.min(2, firstTable.length));
      const result = runCompletion(`SELECT ${prefix}`);
      expect(result[0]?.label).toBe(firstTable);
    });

    it('ranks base table column first for qualifier access', () => {
      const expected = [...primaryColumns].sort((a, b) =>
        a.localeCompare(b)
      )[0];
      const result = runCompletion(`SELECT ${primaryTable.name}.`);
      expect(result[0]?.label).toBe(expected);
    });

    it('ranks alias columns first for alias qualifier access', () => {
      if (!primaryAlias || primaryAliasColumns.length === 0) {
        return;
      }
      const expected = [...primaryAliasColumns].sort((a, b) =>
        a.localeCompare(b)
      )[0];
      const result = runCompletion(`SELECT ${primaryAlias}.`);
      expect(result[0]?.label).toBe(expected);
    });

    it('ranks secondary table column first for qualifier access', () => {
      const expected = [...secondaryColumns].sort((a, b) =>
        a.localeCompare(b)
      )[0];
      const result = runCompletion(`SELECT ${secondaryTable.name}.`);
      expect(result[0]?.label).toBe(expected);
    });

    it('ranks secondary alias column first for qualifier access', () => {
      if (!secondaryAlias || secondaryAliasColumns.length === 0) {
        return;
      }
      const expected = [...secondaryAliasColumns].sort((a, b) =>
        a.localeCompare(b)
      )[0];
      const result = runCompletion(`SELECT ${secondaryAlias}.`);
      expect(result[0]?.label).toBe(expected);
    });

    it('ranks columns first inside WHERE clause', () => {
      const expected = [...primaryColumns].sort((a, b) =>
        a.localeCompare(b)
      )[0];
      const result = runCompletion(
        `SELECT ${primaryTable.name}.id FROM ${primaryTable.name} WHERE `
      );
      expect(result[0]?.label).toBe(expected);
    });

    it('ranks alias columns first inside WHERE clause', () => {
      if (!primaryAlias || primaryAliasColumns.length === 0) {
        return;
      }
      const expected = [...primaryAliasColumns].sort((a, b) =>
        a.localeCompare(b)
      )[0];
      const result = runCompletion(
        `SELECT ${primaryTable.name}.id FROM ${primaryTable.name} ${primaryAlias} WHERE ${primaryAlias}.`
      );
      expect(result[0]?.label).toBe(expected);
    });

    it('ranks columns first inside GROUP BY clause', () => {
      const expected = [...primaryColumns].sort((a, b) =>
        a.localeCompare(b)
      )[0];
      const result = runCompletion(
        `SELECT ${primaryTable.name}.id FROM ${primaryTable.name} GROUP BY `
      );
      expect(result[0]?.label).toBe(expected);
    });

    it('ranks alias columns first inside GROUP BY clause', () => {
      if (!primaryAlias || primaryAliasColumns.length === 0) {
        return;
      }
      const expected = [...primaryAliasColumns].sort((a, b) =>
        a.localeCompare(b)
      )[0];
      const result = runCompletion(
        `SELECT ${primaryAlias}.id, COUNT(*) FROM ${primaryTable.name} ${primaryAlias} GROUP BY ${primaryAlias}.`
      );
      expect(result[0]?.label).toBe(expected);
    });

    it('ranks metadata segments first when drilling down', () => {
      const result = runCompletion('SELECT agent_runs.metadata_json->');
      const metadataLabels = result
        .filter((item) => item.kind === 'metadata')
        .map((item) => item.label)
        .sort((a, b) => a.localeCompare(b));
      expect(metadataLabels[0]).toBe("'foo'");
    });

    it('ranks metadata nested segments first when drilling down', () => {
      const result = runCompletion(
        "SELECT agent_runs.metadata_json->'stats'->"
      );
      const metadataLabels = result
        .filter((item) => item.kind === 'metadata')
        .map((item) => item.label)
        .sort((a, b) => a.localeCompare(b));
      expect(metadataLabels[0]).toBe("'detail'");
    });

    it('ranks OFFSET keyword first after LIMIT prefix', () => {
      const result = runCompletion('SELECT id FROM agent_runs LIMIT 1 OFF');
      expect(result[0]?.label).toBe('OFFSET');
    });

    it('ranks WHEN keyword first with prefix inside CASE expression', () => {
      const result = runCompletion('SELECT CASE W');
      expect(result[0]?.label).toBe('WHEN');
    });

    it('ranks columns ahead inside EXISTS subquery start', () => {
      const expected = [...primaryColumns].sort((a, b) =>
        a.localeCompare(b)
      )[0];
      const result = runCompletion(
        'SELECT id FROM agent_runs WHERE EXISTS (SELECT '
      );
      expect(result[0]?.label).toBe(expected);
    });
  });
});
