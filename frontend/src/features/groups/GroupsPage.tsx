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
      <h1>{t('groups.title')}</h1>

      <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid">
        <h2>{t('groups.create')}</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (!name.trim()) return
            createGroup.mutate(name, { onSuccess: () => setName('') })
          }}
        >
          <div className="flex max-w-[480px] flex-wrap gap-3 [&>*]:min-w-[140px] [&>*]:flex-1">
            <input
              placeholder={t('groups.name')}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <button type="submit" disabled={createGroup.isPending}>
              {t('groups.create')}
            </button>
          </div>
        </form>
      </div>

      <div className="mb-5 rounded-[10px] border border-border bg-surface p-4 print:mb-3 print:break-inside-avoid">
        <h2>{t('groups.title')}</h2>
        {!groups || groups.length === 0 ? (
          <p className="text-muted">{t('groups.noGroups')}</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>{t('groups.name')}</th>
                <th>{t('groups.members')}</th>
                <th>{t('groups.invite')}</th>
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => (
                <tr key={g.id}>
                  <td>
                    {g.name}{' '}
                    {g.is_owner && <span className="inline-block rounded-full border border-border bg-surface-2 px-2 py-0.5 text-xs">{t('groups.owner')}</span>}
                  </td>
                  <td>{g.member_count}</td>
                  <td>
                    <div className="flex min-w-[260px] flex-wrap gap-3 [&>*]:min-w-[140px] [&>*]:flex-1">
                      <input
                        placeholder={t('groups.inviteEmail')}
                        value={inviteEmail[g.id] ?? ''}
                        onChange={(e) =>
                          setInviteEmail((m) => ({ ...m, [g.id]: e.target.value }))
                        }
                      />
                      <button
                        className="border border-border bg-transparent text-text"
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
        <h2>{t('groups.invitations')}</h2>
        {!invitations || invitations.length === 0 ? (
          <p className="text-muted">{t('groups.noInvitations')}</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>{t('groups.name')}</th>
                <th>{t('groups.from')}</th>
                <th>{t('demos.status')}</th>
                <th>{t('demos.created')}</th>
                <th>{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody>
              {invitations.map((inv) => (
                <tr key={inv.id}>
                  <td>{inv.group_name}</td>
                  <td className="text-muted">{inv.inviter_email}</td>
                  <td>
                    <span className="inline-block rounded-full border border-border bg-surface-2 px-2 py-0.5 text-xs">{inv.status}</span>
                  </td>
                  <td className="text-muted">{formatDate(inv.created_at)}</td>
                  <td>
                    {inv.status === 'pending' && (
                      <div className="flex min-w-[200px] flex-wrap gap-3 [&>*]:min-w-[140px] [&>*]:flex-1">
                        <button
                          onClick={() => respond.mutate({ id: inv.id, accept: true })}
                          disabled={respond.isPending}
                        >
                          {t('groups.accept')}
                        </button>
                        <button
                          className="border border-border bg-transparent text-text"
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
