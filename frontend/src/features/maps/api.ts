import { api } from '@/lib/apiClient'
import type { MapOut } from '@/types/api'

export const mapsApi = {
  list: () => api.get<MapOut[]>('/maps'),
}
