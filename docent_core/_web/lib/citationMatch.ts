import { Citation } from '@/app/types/experimentViewerTypes';
import { generateCitationId } from './citationUtils';

export interface Interval {
  start: number;
  end: number;
  id: string; // citation id
}

// Simple capped cache (LRU-ish) keyed by text + citations signature
const MAX_CACHE_ENTRIES = 100;
const cache = new Map<string, Interval[]>();

const escapeForRegex = (input: string): string => {
  return input.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
};

const buildWhitespaceFlexibleRegex = (pattern: string): RegExp => {
  let out = '';
  let i = 0;
  while (i < pattern.length) {
    const ch = pattern[i];
    if (/\s/.test(ch)) {
      while (i < pattern.length && /\s/.test(pattern[i])) i++;
      out += '\\s+';
      continue;
    }
    out += escapeForRegex(ch);
    i++;
  }
  return new RegExp(out, 'g');
};

const simpleHash = (s: string): string => {
  // Lightweight non-crypto hash
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h * 31 + s.charCodeAt(i)) | 0;
  }
  return String(h >>> 0);
};

const buildKey = (text: string, citations: Citation[]): string => {
  const textHash = simpleHash(text);
  // Only include fields relevant to matching to keep key stable and small
  const sig = citations
    .map((c) => `${c.transcript_idx}-${c.block_idx}-${c.start_pattern ?? ''}`)
    .join(';');
  return `${textHash}::${sig}`;
};

const CAP_MATCHES_PER_CITATION = 200;

const findMatchesForCitation = (
  text: string,
  citation: Citation
): Interval[] => {
  const id = generateCitationId(citation);
  const result: Interval[] = [];
  const { start_pattern } = citation;
  if (!start_pattern) return result;

  const startRe = buildWhitespaceFlexibleRegex(start_pattern);
  let m: RegExpExecArray | null;
  while ((m = startRe.exec(text)) !== null) {
    if (m[0].length === 0) {
      startRe.lastIndex++;
      continue;
    }
    result.push({ start: m.index, end: m.index + m[0].length, id });
    if (result.length >= CAP_MATCHES_PER_CITATION) break;
  }
  return result;
};

export const computeCitationIntervals = (
  text: string,
  citations: Citation[]
): Interval[] => {
  if (!citations || citations.length === 0) return [];
  const key = buildKey(text, citations);
  const cached = cache.get(key);
  if (cached) return cached;

  const intervals: Interval[] = [];
  for (const c of citations) {
    const matches = findMatchesForCitation(text, c);
    if (matches.length) intervals.push(...matches);
  }

  // Cache with simple eviction
  if (cache.size >= MAX_CACHE_ENTRIES) {
    const firstKey = cache.keys().next().value;
    if (firstKey) {
      cache.delete(firstKey);
    }
  }
  cache.set(key, intervals);
  return intervals;
};
