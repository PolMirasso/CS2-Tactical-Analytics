import { api } from '@/lib/apiClient'
import type { PlayerHit, PlayerProfile } from '@/types/api'

export const playersApi = {
  search: (term: string) =>
    api.get<PlayerHit[]>(`/hltv/players/search?term=${encodeURIComponent(term)}`),
  profile: (id: string, refresh = false) =>
    api.get<PlayerProfile>(`/hltv/players/${encodeURIComponent(id)}${refresh ? '?refresh=true' : ''}`),
}
