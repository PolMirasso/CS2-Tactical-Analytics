import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { FilterSupportParams, PredictIn } from '@/types/api'
import { scoutingApi } from './api'
import type { DateWindow } from './period'

export function useTendencies(
  mapId: string | undefined,
  teams: string[] | undefined,
  dateWindow?: DateWindow,
) {
  return useQuery({
    queryKey: ['scouting', 'tendencies', mapId, teams, dateWindow],
    queryFn: () => scoutingApi.tendencies(mapId!, teams, dateWindow),
    enabled: !!mapId,
    staleTime: 60_000,
  })
}

// rounds backing the current filters
export function useFilterSupport(params: FilterSupportParams | undefined) {
  return useQuery({
    queryKey: ['scouting', 'support', params],
    queryFn: () => scoutingApi.support(params!),
    enabled: !!params?.map_id,
    staleTime: 60_000,
  })
}

export function useModelStatus() {
  return useQuery({
    queryKey: ['scouting', 'model'],
    queryFn: () => scoutingApi.model(),
    staleTime: 30_000,
  })
}

export function usePredict() {
  return useMutation({ mutationFn: (payload: PredictIn) => scoutingApi.predict(payload) })
}

export function useTrainModel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => scoutingApi.train(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['scouting', 'model'] }),
  })
}

// evaluates without persisting
export function useEvaluateMaps() {
  return useMutation({ mutationFn: () => scoutingApi.evaluate() })
}
