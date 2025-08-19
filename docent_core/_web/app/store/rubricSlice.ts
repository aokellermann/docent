import { createSlice } from '@reduxjs/toolkit';
import { rubricApi } from '../api/rubricApi';
import { Citation } from '../types/experimentViewerTypes';

export interface Rubric {
  id: string;
  version: number;
  high_level_description: string;
  inclusion_rules: string[];
  exclusion_rules: string[];
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

export interface RubricState {
  activeRubricId: string | null;
  editingRubricId: string | null;
  latestRubricsMap: Record<string, Rubric>; // rubric_id -> latest version of Rubric
}

const initialState: RubricState = {
  activeRubricId: null,
  editingRubricId: null,
  latestRubricsMap: {},
};

// Helper function to convert rubrics array to map
const convertRubricsArrayToMap = (
  rubrics: Rubric[]
): Record<string, Rubric> => {
  return rubrics.reduce(
    (acc, rubric) => {
      acc[rubric.id] = rubric;
      return acc;
    },
    {} as Record<string, Rubric>
  );
};

const convertCentroidsArrayToMap = (
  centroids: RubricCentroid[]
): Record<string, RubricCentroid> => {
  return centroids.reduce(
    (acc, centroid) => {
      acc[centroid.id] = centroid;
      return acc;
    },
    {} as Record<string, RubricCentroid>
  );
};

export const rubricSlice = createSlice({
  name: 'rubric',
  initialState,
  reducers: {
    setActiveRubricId(state, action) {
      state.activeRubricId = action.payload;
    },
    setEditingRubricId(state, action) {
      state.editingRubricId = action.payload;
    },
    setRubricsMap(state, action) {
      state.latestRubricsMap = action.payload;
    },
    setRubric(state, action) {
      state.latestRubricsMap[action.payload.id] = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      // Handle getRubrics fulfilled
      .addMatcher(
        rubricApi.endpoints.getRubrics.matchFulfilled,
        (state, action) => {
          state.latestRubricsMap = convertRubricsArrayToMap(action.payload);
        }
      )
      // Handle deleteRubric fulfilled
      .addMatcher(
        rubricApi.endpoints.deleteRubric.matchFulfilled,
        (state, action) => {
          state.activeRubricId = null;
        }
      );
  },
});

export const {
  setActiveRubricId,
  setEditingRubricId,
  setRubricsMap,
  setRubric,
} = rubricSlice.actions;

export default rubricSlice.reducer;
