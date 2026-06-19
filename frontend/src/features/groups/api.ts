import { api } from '@/lib/apiClient'
import type { GroupOut, InvitationOut } from '@/types/api'

export const groupsApi = {
  list: () => api.get<GroupOut[]>('/groups'),
  create: (name: string) => api.post<GroupOut>('/groups', { name }),
  invite: (groupId: number, email: string) =>
    api.post<InvitationOut>(`/groups/${groupId}/invite`, { email }),
  invitations: () => api.get<InvitationOut[]>('/invitations'),
  respond: (invitationId: number, accept: boolean) =>
    api.post<void>(`/invitations/${invitationId}/respond?accept=${accept}`),
}
