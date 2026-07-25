import { api, qs } from '@/lib/apiClient'
import type {
  DateWindowParams,
  SiteDistributionOut,
  SiteDistributionParams,
  TeamRef,
  TeamRostersOut,
} from '@/types/api'

export const analyticsApi = {
  teams: (mapId: string) => api.get<TeamRef[]>(`/analytics/teams${qs({ map_id: mapId })}`),
  siteDistribution: (params: SiteDistributionParams) =>
    api.get<SiteDistributionOut>(`/analytics/site-distribution${qs(params)}`),
  roster: (mapId: string, team: string, dateWindow?: DateWindowParams) =>
    api.get<TeamRostersOut>(`/analytics/roster${qs({ map_id: mapId, team, ...dateWindow })}`),
}
