import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { PredictIn } from '@/types/api'
import { scoutingApi } from './api'

export function useTendencies(mapId: string | undefined, teams: string[] | undefined) {
  return useQuery({
    queryKey: ['scouting', 'tendencies', mapId, teams],
    queryFn: () => scoutingApi.tendencies(mapId!, teams),
    enabled: !!mapId,
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
