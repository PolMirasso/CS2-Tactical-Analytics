import { api, qs } from '@/lib/apiClient'
import type { ModelStatusOut, PredictIn, PredictOut, TendenciesOut } from '@/types/api'

export const scoutingApi = {
  predict: (payload: PredictIn) => api.post<PredictOut>('/scouting/predict', payload),
  tendencies: (mapId: string, team?: string[]) =>
    api.get<TendenciesOut>(`/scouting/tendencies${qs({ map_id: mapId, team })}`),
  model: () => api.get<ModelStatusOut>('/scouting/model'),
  train: () => api.post<ModelStatusOut>('/scouting/train'),
}
