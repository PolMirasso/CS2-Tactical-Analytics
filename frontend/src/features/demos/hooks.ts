import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { demosApi } from './api'

const KEY = ['demos']

export function useDemos() {
  return useQuery({ queryKey: KEY, queryFn: demosApi.list })
}

export function useDemo(id: number) {
  return useQuery({ queryKey: [...KEY, id], queryFn: () => demosApi.get(id) })
}

export function useDemoAnalysis(id: number) {
  return useQuery({
    queryKey: [...KEY, id, 'analysis'],
    queryFn: () => demosApi.analysis(id),
  })
}

export function useReplayMeta(id: number) {
  return useQuery({
    queryKey: [...KEY, id, 'replay'],
    queryFn: () => demosApi.replayMeta(id),
    retry: false, // 404 simply means the demo has no replay artifact yet
  })
}

export function useReplayRound(id: number, round: number | null) {
  return useQuery({
    queryKey: [...KEY, id, 'replay', round],
    queryFn: () => demosApi.replayRound(id, round as number),
    enabled: round != null,
  })
}

export function useUploadDemo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (form: FormData) => demosApi.upload(form),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useReparseDemo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => demosApi.reparse(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useDeleteDemo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => demosApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}
