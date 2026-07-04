import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { DownloadDemosIn } from '@/types/api'
import { hltvApi } from './api'

const JOBS_KEY = ['hltv', 'jobs']

export function useDownloadJobs() {
  return useQuery({
    queryKey: JOBS_KEY,
    queryFn: hltvApi.listJobs,
    // Poll while any job is still pending/running so progress updates live.
    refetchInterval: (query) => {
      const jobs = query.state.data ?? []
      const active = jobs.some(
        (j) =>
          j.status === 'running' ||
          j.status === 'pending' ||
          j.status === 'cancelling',
      )
      return active ? 2000 : false
    },
  })
}

export function useStartDownload() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: DownloadDemosIn) => hltvApi.startDownload(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: JOBS_KEY }),
  })
}

type JobAction = 'pause' | 'resume' | 'cancel' | 'retry'

const JOB_ACTIONS = {
  pause: hltvApi.pauseJob,
  resume: hltvApi.resumeJob,
  cancel: hltvApi.cancelJob,
  retry: hltvApi.retryJob,
}

export function useJobAction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: JobAction }) =>
      JOB_ACTIONS[action](id),
    onSuccess: () => qc.invalidateQueries({ queryKey: JOBS_KEY }),
  })
}
