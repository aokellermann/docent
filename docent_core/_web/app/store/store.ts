// store.ts

import { configureStore } from '@reduxjs/toolkit';

import experimentViewerReducer from './experimentViewerSlice';
import collectionReducer from './collectionSlice';
import toastReducer from './toastSlice';
import transcriptReducer from './transcriptSlice';
import { diffReducer } from './diffSlice';
import embedReducer from './embedSlice';
import { collabApi } from '@/lib/permissions/collabSlice';
import { chartApi } from '../api/chartApi';
import { diffApi } from '../api/diffApi';
import { rubricApi } from '../api/rubricApi';
import rubricReducer from './rubricSlice';
import { collectionApi } from '../api/collectionApi';
import { refinementApi } from '../api/refinementApi';
import refinementReducer from './refinementSlice';

const store = configureStore({
  reducer: {
    experimentViewer: experimentViewerReducer,
    rubric: rubricReducer,
    embed: embedReducer,
    diff: diffReducer,
    collection: collectionReducer,
    transcript: transcriptReducer,
    toast: toastReducer,
    refinement: refinementReducer,
    [collabApi.reducerPath]: collabApi.reducer,
    [chartApi.reducerPath]: chartApi.reducer,
    [diffApi.reducerPath]: diffApi.reducer,
    [rubricApi.reducerPath]: rubricApi.reducer,
    [collectionApi.reducerPath]: collectionApi.reducer,
    [refinementApi.reducerPath]: refinementApi.reducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware()
      .concat(collabApi.middleware)
      .concat(chartApi.middleware)
      .concat(diffApi.middleware)
      .concat(rubricApi.middleware)
      .concat(collectionApi.middleware)
      .concat(refinementApi.middleware),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

export default store;
