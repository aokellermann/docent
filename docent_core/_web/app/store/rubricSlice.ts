import { createSlice } from '@reduxjs/toolkit';
import { Citation } from '../types/experimentViewerTypes';

export interface JudgeModel {
  provider: string;
  model_name: string;
  reasoning_effort: 'low' | 'medium' | 'high' | null;
  uses_byok?: boolean;
}

export interface Rubric {
  id: string;
  version: number;
  rubric_text: string;
  judge_model: JudgeModel | null;
}

export interface JudgeResult {
  id: string;
  agent_run_id: string;
  rubric_id: string;
  value: string | null;
}

export interface JudgeResultWithCitations extends JudgeResult {
  citations: Citation[] | null;
}

export interface RubricCentroid {
  id: string;
  collection_id: string;
  rubric_id: string;
  centroid: string;
}

export interface RubricState {}

const initialState: RubricState = {};

export const rubricSlice = createSlice({
  name: 'rubric',
  initialState,
  reducers: {},
});

// export const {} = rubricSlice.actions;

export default rubricSlice.reducer;
