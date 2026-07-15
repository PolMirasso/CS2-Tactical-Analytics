import { useQuery } from '@tanstack/react-query'
import type { SiteDistributionParams } from '@/types/api'
import { analyticsApi } from './api'

export function useTeams(mapId: string | undefined) {
  return useQuery({
    queryKey: ['analytics', 'teams', mapId],
    queryFn: () => analyticsApi.teams(mapId!),
    enabled: !!mapId,
    staleTime: 60_000,
  })
}

export function useSiteDistribution(params: SiteDistributionParams | undefined) {
  return useQuery({
    queryKey: ['analytics', 'site-distribution', params],
    queryFn: () => analyticsApi.siteDistribution(params!),
    enabled: !!params?.map_id,
  })
}

export function useTeamRoster(mapId: string | undefined, team: string | undefined) {
  return useQuery({
    queryKey: ['analytics', 'roster', mapId, team],
    queryFn: () => analyticsApi.roster(mapId!, team!),
    enabled: !!mapId && !!team,
    staleTime: 60_000,
  })
}
