import { api } from '@/lib/apiClient'
import type { SiteDistributionOut, SiteDistributionParams } from '@/types/api'

function buildQuery(params: SiteDistributionParams): string {
  const sp = new URLSearchParams()
  sp.set('map_id', params.map_id)
  if (params.team) sp.set('team', params.team)
  if (params.date_from) sp.set('date_from', params.date_from)
  if (params.date_to) sp.set('date_to', params.date_to)
  // FastAPI reads repeated keys as a list[str].
  for (const b of params.buy_type ?? []) sp.append('buy_type', b)
  return sp.toString()
}

export const analyticsApi = {
  teams: (mapId: string) =>
    api.get<string[]>(`/analytics/teams?map_id=${encodeURIComponent(mapId)}`),
  siteDistribution: (params: SiteDistributionParams) =>
    api.get<SiteDistributionOut>(`/analytics/site-distribution?${buildQuery(params)}`),
}
