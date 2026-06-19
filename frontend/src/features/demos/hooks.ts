import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { demosApi } from './api'

const KEY = ['demos']

export function useDemos() {
  return useQuery({ queryKey: KEY, queryFn: demosApi.list })
}

export function useDemo(id: number) {
  return useQuery({ queryKey: [...KEY, id], queryFn: () => demosApi.get(id) })
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
