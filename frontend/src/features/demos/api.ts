import { api } from '@/lib/apiClient'
import type {
  DemoAnalysisOut,
  DemoListOut,
  DemoListParams,
  DemoOut,
  ReplayMetaOut,
  ReplayRound,
  UploadResult,
} from '@/types/api'

function qs(params: Record<string, string | number | undefined>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '') sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

export const demosApi = {
  list: (params: DemoListParams = {}) => api.get<DemoListOut>(`/demos${qs(params)}`),
  get: (id: number) => api.get<DemoOut>(`/demos/${id}`),
  analysis: (id: number) => api.get<DemoAnalysisOut>(`/demos/${id}/analysis`),
  replayMeta: (id: number) => api.get<ReplayMetaOut>(`/demos/${id}/replay`),
  replayRound: (id: number, round: number) =>
    api.get<ReplayRound>(`/demos/${id}/replay/${round}`),
  upload: (form: FormData) => api.postForm<UploadResult>('/demos/upload', form),
  reparse: (id: number) => api.post<UploadResult>(`/demos/${id}/parse`),
  remove: (id: number) => api.del<void>(`/demos/${id}`),
}
