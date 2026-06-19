import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { groupsApi } from './api'

const GROUPS_KEY = ['groups']
const INVITES_KEY = ['invitations']

export function useGroups() {
  return useQuery({ queryKey: GROUPS_KEY, queryFn: groupsApi.list })
}

export function useInvitations() {
  return useQuery({ queryKey: INVITES_KEY, queryFn: groupsApi.invitations })
}

export function useCreateGroup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => groupsApi.create(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: GROUPS_KEY }),
  })
}

export function useInviteMember() {
  return useMutation({
    mutationFn: ({ groupId, email }: { groupId: number; email: string }) =>
      groupsApi.invite(groupId, email),
  })
}

export function useRespondInvitation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, accept }: { id: number; accept: boolean }) =>
      groupsApi.respond(id, accept),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: INVITES_KEY })
      qc.invalidateQueries({ queryKey: GROUPS_KEY })
    },
  })
}
