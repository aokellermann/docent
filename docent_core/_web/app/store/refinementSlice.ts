import { createSlice } from '@reduxjs/toolkit';
import { ChatMessage } from '@/app/types/transcriptTypes';
import { JudgeResultWithCitations } from './rubricSlice';

export type RefinementStatus =
  | 'reading_data'
  | 'initial_feedback'
  | 'asking_questions'
  | 'done';

export interface RefinementAgentSession {
  id: string;
  rubric_id: string;
  rubric_version: number;
  messages: ChatMessage[];
  status: RefinementStatus;
  judge_results: JudgeResultWithCitations[];
}

interface RefinementState {}

const initialState: RefinementState = {};

const refinementSlice = createSlice({
  name: 'refinement',
  initialState,
  reducers: {},
  extraReducers: (builder) => {},
});

// export const {} = refinementSlice.actions;
export default refinementSlice.reducer;
