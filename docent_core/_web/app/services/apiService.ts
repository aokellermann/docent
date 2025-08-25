import axios from 'axios';

import { BASE_URL } from '@/app/constants';

export const apiBaseClient = axios.create({
  baseURL: `${BASE_URL}`,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});

export const apiRestClient = axios.create({
  baseURL: `${BASE_URL}/rest`,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});
