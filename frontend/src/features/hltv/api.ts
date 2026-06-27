import { api } from '@/lib/apiClient'
import type { DownloadDemosIn, DownloadJobOut, TeamHit } from '@/types/api'

export const hltvApi = {
  searchTeams: (term: string) =>
    api.get<TeamHit[]>(`/hltv/search?term=${encodeURIComponent(term)}`),
  startDownload: (body: DownloadDemosIn) =>
    api.post<DownloadJobOut>('/hltv/download', body),
  listJobs: () => api.get<DownloadJobOut[]>('/hltv/downloads'),
  pauseJob: (id: string) =>
    api.post<DownloadJobOut>(`/hltv/download/${id}/pause`, {}),
  resumeJob: (id: string) =>
    api.post<DownloadJobOut>(`/hltv/download/${id}/resume`, {}),
  cancelJob: (id: string) =>
    api.post<DownloadJobOut>(`/hltv/download/${id}/cancel`, {}),
  retryJob: (id: string) =>
    api.post<DownloadJobOut>(`/hltv/download/${id}/retry`, {}),
}
