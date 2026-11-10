ACCOUNT_CREATED = "account.created"
ACCOUNT_APPROVED = "account.approved"
ACCOUNT_PROMOTED = "account.promoted"
ACCOUNT_DEMOTED = "account.demoted"
ACCOUNT_DEACTIVATED = "account.deactivated"
ACCOUNT_REACTIVATED = "account.reactivated"
ACCOUNT_RESET = "account.reset"
ACCOUNT_PASSWORD_SET = "account.password_set"
ACCOUNT_MFA_ENROLLED = "account.mfa_enrolled"
ACCOUNT_LOCKED = "account.locked"
SUBJECT_CREATED = "subject.created"
SUBJECT_RENAMED = "subject.renamed"
SUBJECT_DEACTIVATED = "subject.deactivated"
SUBJECT_REACTIVATED = "subject.reactivated"
ROSTER_UPLOADED = "roster.uploaded"
ROSTER_APPLIED = "roster.applied"
ROSTER_DISCARDED = "roster.discarded"
GROUP_CREATED = "group.created"
GROUP_COURSE_CHANGED = "group.course_changed"
GROUP_LOCKED = "group.locked"
GROUP_UNLOCKED = "group.unlocked"
GROUP_ARCHIVED = "group.archived"
GROUP_UNARCHIVED = "group.unarchived"
GROUP_DELETED = "group.deleted"
CADET_ADDED = "cadet.added"
CADET_RENAMED = "cadet.renamed"
CADET_DEACTIVATED = "cadet.deactivated"
CADET_REACTIVATED = "cadet.reactivated"
CADET_DELETED = "cadet.deleted"
SCORE_CHANGED = "score.changed"
COMMENT_CHANGED = "comment.changed"
EXPORT_DOWNLOADED = "export.downloaded"
PROGRAMME_CREATED = "programme.created"
PROGRAMME_RENAMED = "programme.renamed"
PROGRAMME_DEACTIVATED = "programme.deactivated"
PROGRAMME_REACTIVATED = "programme.reactivated"
GROUP_PROGRAMME_CHANGED = "group.programme_changed"
SUBJECT_ASSIGNED = "subject.assigned"
SUBJECT_UNASSIGNED = "subject.unassigned"
CADET_SUBJECT_REMOVED = "cadet.subject_removed"
CADET_SUBJECT_RESTORED = "cadet.subject_restored"
ACCOUNT_ADMIN_TRANSFERRED = "account.admin_transferred"

ALL_ACTIONS = [
    ACCOUNT_CREATED,
    ACCOUNT_APPROVED,
    ACCOUNT_PROMOTED,
    ACCOUNT_DEMOTED,
    ACCOUNT_DEACTIVATED,
    ACCOUNT_REACTIVATED,
    ACCOUNT_RESET,
    ACCOUNT_PASSWORD_SET,
    ACCOUNT_MFA_ENROLLED,
    ACCOUNT_LOCKED,
    SUBJECT_CREATED,
    SUBJECT_RENAMED,
    SUBJECT_DEACTIVATED,
    SUBJECT_REACTIVATED,
    ROSTER_UPLOADED,
    ROSTER_APPLIED,
    ROSTER_DISCARDED,
    GROUP_CREATED,
    GROUP_COURSE_CHANGED,
    GROUP_LOCKED,
    GROUP_UNLOCKED,
    GROUP_ARCHIVED,
    GROUP_UNARCHIVED,
    GROUP_DELETED,
    CADET_ADDED,
    CADET_RENAMED,
    CADET_DEACTIVATED,
    CADET_REACTIVATED,
    CADET_DELETED,
    SCORE_CHANGED,
    COMMENT_CHANGED,
    EXPORT_DOWNLOADED,
    PROGRAMME_CREATED,
    PROGRAMME_RENAMED,
    PROGRAMME_DEACTIVATED,
    PROGRAMME_REACTIVATED,
    GROUP_PROGRAMME_CHANGED,
    SUBJECT_ASSIGNED,
    SUBJECT_UNASSIGNED,
    CADET_SUBJECT_REMOVED,
    CADET_SUBJECT_RESTORED,
    ACCOUNT_ADMIN_TRANSFERRED,
]

ACTION_CHOICES = [(a, a) for a in ALL_ACTIONS]
