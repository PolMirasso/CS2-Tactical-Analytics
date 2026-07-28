import { api, qs } from '@/lib/apiClient'
import type {
  FilterSupportOut,
  FilterSupportParams,
  ModelStatusOut,
  PredictIn,
  PredictOut,
  TendenciesOut,
} from '@/types/api'
import type { DateWindow } from './period'

export const scoutingApi = {
  predict: (payload: PredictIn) => api.post<PredictOut>('/scouting/predict', payload),
  tendencies: (mapId: string, team?: string[], dateWindow?: DateWindow, roster?: string) =>
    api.get<TendenciesOut>(
      `/scouting/tendencies${qs({ map_id: mapId, team, ...dateWindow, roster })}`,
    ),
  support: (params: FilterSupportParams) =>
    api.get<FilterSupportOut>(`/scouting/support${qs(params)}`),
  model: () => api.get<ModelStatusOut>('/scouting/model'),
  train: () => api.post<ModelStatusOut>('/scouting/train'),
  evaluate: () => api.post<ModelStatusOut>('/scouting/evaluate'),
}
