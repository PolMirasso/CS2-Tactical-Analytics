import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { PlayerProfile } from '@/types/api'
import { playersApi } from './api'

const profileKey = (id: string) => ['players', 'profile', id]

export function usePlayerSearch(term: string) {
  return useQuery({
    queryKey: ['players', 'search', term],
    queryFn: () => playersApi.search(term),
    enabled: term.trim().length >= 2,
  })
}

export function usePlayerProfile(id: string | undefined) {
  return useQuery({
    queryKey: profileKey(id ?? ''),
    queryFn: () => playersApi.profile(id as string),
    enabled: Boolean(id),
    retry: false,
    staleTime: Infinity,
  })
}

export function useRefreshPlayer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => playersApi.profile(id, true),
    onSuccess: (data: PlayerProfile) => qc.setQueryData(profileKey(data.id), data),
  })
}
