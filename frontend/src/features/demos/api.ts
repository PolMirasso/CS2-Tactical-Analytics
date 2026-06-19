import { api } from '@/lib/apiClient'
import type { DemoOut, UploadResult } from '@/types/api'

export const demosApi = {
  list: () => api.get<DemoOut[]>('/demos'),
  get: (id: number) => api.get<DemoOut>(`/demos/${id}`),
  upload: (form: FormData) => api.postForm<UploadResult>('/demos/upload', form),
  reparse: (id: number) => api.post<UploadResult>(`/demos/${id}/parse`),
  remove: (id: number) => api.del<void>(`/demos/${id}`),
}
