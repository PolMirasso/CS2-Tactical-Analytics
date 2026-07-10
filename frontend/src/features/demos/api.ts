import { api, qs } from '@/lib/apiClient'
import type {
  DemoAnalysisOut,
  DemoListOut,
  DemoListParams,
  DemoOut,
  ReparseStatus,
  ReplayMetaOut,
  ReplayRound,
  UploadResult,
} from '@/types/api'

export const demosApi = {
  list: (params: DemoListParams = {}) => api.get<DemoListOut>(`/demos${qs(params)}`),
  get: (id: number) => api.get<DemoOut>(`/demos/${id}`),
  analysis: (id: number) => api.get<DemoAnalysisOut>(`/demos/${id}/analysis`),
  replayMeta: (id: number) => api.get<ReplayMetaOut>(`/demos/${id}/replay`),
  replayRound: (id: number, round: number) =>
    api.get<ReplayRound>(`/demos/${id}/replay/${round}`),
  upload: (form: FormData) => api.postForm<UploadResult>('/demos/upload', form),
  reparse: (id: number) => api.post<UploadResult>(`/demos/${id}/parse`),
  reparseAll: (mapId?: string) =>
    api.post<ReparseStatus>(`/demos/reparse-all${qs({ map_id: mapId })}`),
  reparseAllStatus: () => api.get<ReparseStatus>('/demos/reparse-all/status'),
  remove: (id: number) => api.del<void>(`/demos/${id}`),
}
