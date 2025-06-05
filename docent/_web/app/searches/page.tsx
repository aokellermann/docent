'use client';

import { useEffect } from 'react';

import { Separator } from '@/components/ui/separator';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

import { UserProfile } from '../components/auth/UserProfile';
import { useAppDispatch, useAppSelector } from '../store/hooks';
import { fetchJobs } from '../store/jobsSlice';

export default function JobsPage() {
  const dispatch = useAppDispatch();

  useEffect(() => {
    dispatch(fetchJobs());
  }, []);

  const jobs = useAppSelector((state) => state.jobs.jobs);

  return (
    <div className="container mx-auto py-4 px-3 max-w-screen-xl">
      <div className="space-y-1 mb-4">
        <div className="flex justify-between items-center">
          <div>
            <div className="text-lg font-semibold tracking-tight">Search jobs</div>
          </div>
          <div className="flex items-center gap-2">
            <UserProfile />
          </div>
        </div>
      </div>

      <Separator className="my-4" />

      <Table>
        <TableHeader className="bg-gray-50 sticky top-0">
          <TableRow>
            <TableHead className="w-[5%] py-2.5 font-medium text-xs text-gray-500">
              FrameGrid ID
            </TableHead>
            <TableHead className="w-[5%] py-2.5 font-medium text-xs text-gray-500">
              Started at
            </TableHead>
            <TableHead className="w-[5%] py-2.5 font-medium text-xs text-gray-500">
              Progress
            </TableHead>
            <TableHead className="w-[40%] py-2.5 font-medium text-xs text-gray-500">
              Query
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {jobs.map(([_, query]) => {
            return (
              <TableRow>
                <TableCell>
                  <span className="font-mono text-gray-600 text-xs">
                    {query.fg_id.split('-')[0]}
                  </span>
                </TableCell>
                <TableCell>todo</TableCell>
                <TableCell>todo</TableCell>
                <TableCell>{query.search_query}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
