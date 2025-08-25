/**
 * Note(mengk): the patterns in this file are highly deprecated!
 * This is not very "React-ive" - having global state like this and using async thunks is highly discouraged.
 */

import { createSlice, type PayloadAction } from '@reduxjs/toolkit';

export interface ExperimentViewerState {
  experimentViewerScrollPosition?: number;
  // paginationState?: ;
}

const initialState: ExperimentViewerState = {};

export const experimentViewerSlice = createSlice({
  name: 'experimentViewer',
  initialState,
  reducers: {
    setExperimentViewerScrollPosition: (
      state,
      action: PayloadAction<number>
    ) => {
      state.experimentViewerScrollPosition = action.payload;
    },
  },
});

export const { setExperimentViewerScrollPosition } =
  experimentViewerSlice.actions;

export default experimentViewerSlice.reducer;
