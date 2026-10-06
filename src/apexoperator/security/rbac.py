from enum import Enum


class Role(str, Enum):
    AP_CLERK = "AP_CLERK"
    FINANCE_MANAGER = "FINANCE_MANAGER"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"


class Permission(str, Enum):
    INVOICE_READ = "invoice:read"
    INVOICE_VALIDATE = "invoice:validate"
    INVOICE_RECALCULATE = "invoice:recalculate"
    APPROVAL_SUBMIT = "approval:submit"
    APPROVAL_APPROVE = "approval:approve"
    APPROVAL_REJECT = "approval:reject"
    DISCREPANCY_ESCALATE = "discrepancy:escalate"
    AUDIT_READ = "audit:read"
    AUDIT_VERIFY = "audit:verify"
    SYSTEM_ADMIN = "system:admin"


ROLE_PERMISSIONS = {
    Role.AP_CLERK: frozenset({
        Permission.INVOICE_READ,
        Permission.INVOICE_VALIDATE,
        Permission.INVOICE_RECALCULATE,
        Permission.APPROVAL_SUBMIT,
        Permission.DISCREPANCY_ESCALATE,
    }),
    Role.FINANCE_MANAGER: frozenset({
        Permission.INVOICE_READ,
        Permission.INVOICE_VALIDATE,
        Permission.APPROVAL_APPROVE,
        Permission.APPROVAL_REJECT,
        Permission.DISCREPANCY_ESCALATE,
        Permission.AUDIT_READ,
        Permission.AUDIT_VERIFY,
    }),
    Role.SYSTEM_ADMIN: frozenset(Permission),
}


class RBAC:
    @staticmethod
    def is_allowed(role: Role, permission: Permission) -> bool:
        return permission in ROLE_PERMISSIONS[role]
