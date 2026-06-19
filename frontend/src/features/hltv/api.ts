import { api } from '@/lib/apiClient'
import type { DownloadDemosIn, DownloadJobOut, TeamHit } from '@/types/api'

export const hltvApi = {
  searchTeams: (term: string) =>
    api.get<TeamHit[]>(`/hltv/search?term=${encodeURIComponent(term)}`),
  startDownload: (body: DownloadDemosIn) =>
    api.post<DownloadJobOut>('/hltv/download', body),
  listJobs: () => api.get<DownloadJobOut[]>('/hltv/downloads'),
}
