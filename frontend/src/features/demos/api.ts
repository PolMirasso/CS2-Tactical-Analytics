import { api } from '@/lib/apiClient'
import type {
  DemoAnalysisOut,
  DemoOut,
  ReplayMetaOut,
  ReplayRound,
  UploadResult,
} from '@/types/api'

export const demosApi = {
  list: () => api.get<DemoOut[]>('/demos'),
  get: (id: number) => api.get<DemoOut>(`/demos/${id}`),
  analysis: (id: number) => api.get<DemoAnalysisOut>(`/demos/${id}/analysis`),
  replayMeta: (id: number) => api.get<ReplayMetaOut>(`/demos/${id}/replay`),
  replayRound: (id: number, round: number) =>
    api.get<ReplayRound>(`/demos/${id}/replay/${round}`),
  upload: (form: FormData) => api.postForm<UploadResult>('/demos/upload', form),
  reparse: (id: number) => api.post<UploadResult>(`/demos/${id}/parse`),
  remove: (id: number) => api.del<void>(`/demos/${id}`),
}
