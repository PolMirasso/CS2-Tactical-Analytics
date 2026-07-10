import { api, qs } from '@/lib/apiClient'
import type { SiteDistributionOut, SiteDistributionParams, TeamRef } from '@/types/api'

export const analyticsApi = {
  teams: (mapId: string) => api.get<TeamRef[]>(`/analytics/teams${qs({ map_id: mapId })}`),
  siteDistribution: (params: SiteDistributionParams) =>
    api.get<SiteDistributionOut>(`/analytics/site-distribution${qs(params)}`),
}
