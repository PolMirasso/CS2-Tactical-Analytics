import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { formatDate } from '@/lib/format'
import {
  useCreateGroup,
  useGroups,
  useInvitations,
  useInviteMember,
  useRespondInvitation,
} from './hooks'

export function GroupsPage() {
  const { t } = useTranslation()
  const { data: groups } = useGroups()
  const { data: invitations } = useInvitations()
  const createGroup = useCreateGroup()
  const invite = useInviteMember()
  const respond = useRespondInvitation()

  const [name, setName] = useState('')
  const [inviteEmail, setInviteEmail] = useState<Record<number, string>>({})

  return (
    <div>
      <h1 className="mb-4 text-[1.4rem]">{t('groups.title')}</h1>

      <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid">
        <h2 className="mb-3 text-[1.1rem]">{t('groups.create')}</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (!name.trim()) return
            createGroup.mutate(name, { onSuccess: () => setName('') })
          }}
        >
          <div className="flex max-w-[480px] flex-wrap gap-3 [&>*]:min-w-[140px] [&>*]:flex-1">
            <input
              className="mb-3 w-full rounded-md border border-border bg-surface-2 px-2.5 py-2 font-[inherit] text-text"
              placeholder={t('groups.name')}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <button className="cursor-pointer rounded-md border-none bg-accent px-3.5 py-2 font-[inherit] text-accent-text hover:brightness-[1.08] disabled:cursor-not-allowed disabled:opacity-50" type="submit" disabled={createGroup.isPending}>
              {t('groups.create')}
            </button>
          </div>
        </form>
      </div>

      <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid">
        <h2 className="mb-3 text-[1.1rem]">{t('groups.title')}</h2>
        {!groups || groups.length === 0 ? (
          <p className="my-4 text-muted">{t('groups.noGroups')}</p>
        ) : (
          <table className="w-full border-collapse text-[0.9rem]">
            <thead>
              <tr>
                <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('groups.name')}</th>
                <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('groups.members')}</th>
                <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('groups.invite')}</th>
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => (
                <tr key={g.id}>
                  <td className="border-b border-border px-2.5 py-2 text-left">
                    {g.name}{' '}
                    {g.is_owner && <span className="inline-block rounded-full border border-border bg-surface-2 px-2 py-0.5 text-xs">{t('groups.owner')}</span>}
                  </td>
                  <td className="border-b border-border px-2.5 py-2 text-left">{g.member_count}</td>
                  <td className="border-b border-border px-2.5 py-2 text-left">
                    <div className="flex min-w-[260px] flex-wrap gap-3 [&>*]:min-w-[140px] [&>*]:flex-1">
                      <input
                        className="mb-3 w-full rounded-md border border-border bg-surface-2 px-2.5 py-2 font-[inherit] text-text"
                        placeholder={t('groups.inviteEmail')}
                        value={inviteEmail[g.id] ?? ''}
                        onChange={(e) =>
                          setInviteEmail((m) => ({ ...m, [g.id]: e.target.value }))
                        }
                      />
                      <button
                        className="cursor-pointer rounded-md border border-border bg-transparent px-3.5 py-2 font-[inherit] text-text hover:brightness-[1.08] disabled:cursor-not-allowed disabled:opacity-50"
                        disabled={invite.isPending || !inviteEmail[g.id]}
                        onClick={() =>
                          invite.mutate(
                            { groupId: g.id, email: inviteEmail[g.id] },
                            {
                              onSuccess: () =>
                                setInviteEmail((m) => ({ ...m, [g.id]: '' })),
                            },
                          )
                        }
                      >
                        {t('groups.invite')}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid">
        <h2 className="mb-3 text-[1.1rem]">{t('groups.invitations')}</h2>
        {!invitations || invitations.length === 0 ? (
          <p className="my-4 text-muted">{t('groups.noInvitations')}</p>
        ) : (
          <table className="w-full border-collapse text-[0.9rem]">
            <thead>
              <tr>
                <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('groups.name')}</th>
                <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('groups.from')}</th>
                <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('demos.status')}</th>
                <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('demos.created')}</th>
                <th className="border-b border-border px-2.5 py-2 text-left font-semibold text-muted">{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {invitations.map((inv) => (
                <tr key={inv.id}>
                  <td className="border-b border-border px-2.5 py-2 text-left">{inv.group_name}</td>
                  <td className="border-b border-border px-2.5 py-2 text-left text-muted">{inv.inviter_email}</td>
                  <td className="border-b border-border px-2.5 py-2 text-left">
                    <span className="inline-block rounded-full border border-border bg-surface-2 px-2 py-0.5 text-xs">{inv.status}</span>
                  </td>
                  <td className="border-b border-border px-2.5 py-2 text-left text-muted">{formatDate(inv.created_at)}</td>
                  <td className="border-b border-border px-2.5 py-2 text-left">
                    {inv.status === 'pending' && (
                      <div className="flex min-w-[200px] flex-wrap gap-3 [&>*]:min-w-[140px] [&>*]:flex-1">
                        <button
                          className="cursor-pointer rounded-md border-none bg-accent px-3.5 py-2 font-[inherit] text-accent-text hover:brightness-[1.08] disabled:cursor-not-allowed disabled:opacity-50"
                          onClick={() => respond.mutate({ id: inv.id, accept: true })}
                          disabled={respond.isPending}
                        >
                          {t('groups.accept')}
                        </button>
                        <button
                          className="cursor-pointer rounded-md border border-border bg-transparent px-3.5 py-2 font-[inherit] text-text hover:brightness-[1.08] disabled:cursor-not-allowed disabled:opacity-50"
                          onClick={() => respond.mutate({ id: inv.id, accept: false })}
                          disabled={respond.isPending}
                        >
                          {t('groups.decline')}
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
