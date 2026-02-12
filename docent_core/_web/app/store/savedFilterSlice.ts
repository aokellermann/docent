import { createSlice, type PayloadAction } from '@reduxjs/toolkit';

interface SavedFilterState {
  // surfaceId → active saved filter ID
  activeFilterIds: Record<string, string>;
}

const initialState: SavedFilterState = {
  activeFilterIds: {},
};

const savedFilterSlice = createSlice({
  name: 'savedFilter',
  initialState,
  reducers: {
    setActiveFilterId(
      state,
      action: PayloadAction<{ surfaceId: string; filterId: string }>
    ) {
      state.activeFilterIds[action.payload.surfaceId] = action.payload.filterId;
    },
    clearActiveFilterId(state, action: PayloadAction<string>) {
      delete state.activeFilterIds[action.payload];
    },
  },
});

export const { setActiveFilterId, clearActiveFilterId } =
  savedFilterSlice.actions;

export default savedFilterSlice.reducer;
