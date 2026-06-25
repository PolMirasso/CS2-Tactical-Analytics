import { api } from '@/lib/apiClient'
import type { ModelStatusOut, PredictIn, PredictOut, TendenciesOut } from '@/types/api'

export const scoutingApi = {
  predict: (payload: PredictIn) => api.post<PredictOut>('/scouting/predict', payload),
  tendencies: (mapId: string, team?: string) => {
    const sp = new URLSearchParams({ map_id: mapId })
    if (team) sp.set('team', team)
    return api.get<TendenciesOut>(`/scouting/tendencies?${sp.toString()}`)
  },
  model: () => api.get<ModelStatusOut>('/scouting/model'),
  train: () => api.post<ModelStatusOut>('/scouting/train'),
}
