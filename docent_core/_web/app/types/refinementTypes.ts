import { ChatMessage } from '@/app/types/transcriptTypes';

export interface RefinementAgentSession {
  id: string;
  rubric_id: string;
  rubric_version: number;
  messages: ChatMessage[];
  n_summaries: number;
  // Optional error from backend refinement agent
  error_message?: string;
}
