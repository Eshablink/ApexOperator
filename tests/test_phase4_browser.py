from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright
from apexoperator.audit.ledger import CryptographicAuditLedger
from apexoperator.portal.browser import LocalInvoicePortal, PortalAutomationError
from apexoperator.portal.tools import PortalInvoiceInput, build_portal_tools
from apexoperator.security.rbac import Permission, Role
from apexoperator.tools.registry import RegisteredTool, ToolContext, ToolRegistry

FIXTURE=Path(__file__).parent/'fixtures'/'invoice_portal.html'

@pytest.fixture()
def browser():
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True)
        yield b
        b.close()

def ctx(role=Role.AP_CLERK):
    return ToolContext('tester',role,CryptographicAuditLedger())

def test_read_invoice(browser):
    assert LocalInvoicePortal(browser,FIXTURE).read_invoice('INV-LOW-001') == {'invoice_id':'INV-LOW-001','status':'FOUND','total':'1100.00'}

def test_submit_invoice_verifies_result(browser):
    assert LocalInvoicePortal(browser,FIXTURE).submit_invoice('INV-HIGH-001')['status']=='SUBMITTED'

def test_bad_submit_escalates_as_browser_failure(browser):
    with pytest.raises(PortalAutomationError, match='post-submit verification failed'):
        LocalInvoicePortal(browser,FIXTURE).submit_invoice('UNKNOWN')

def test_browser_tool_uses_registry_and_rbac(browser):
    registry=ToolRegistry(); portal=LocalInvoicePortal(browser,FIXTURE)
    for tool in build_portal_tools(portal): registry.register(tool)
    c=ctx(); result=registry.execute_tool('portal_read_invoice',{'invoice_id':'INV-LOW-001'},c)
    assert result.success and result.data['status']=='FOUND'
    assert c.audit_ledger.verify_integrity()

def test_browser_submit_denied_for_manager(browser):
    registry=ToolRegistry(); portal=LocalInvoicePortal(browser,FIXTURE)
    for tool in build_portal_tools(portal): registry.register(tool)
    c=ctx(Role.FINANCE_MANAGER); result=registry.execute_tool('portal_submit_invoice',{'invoice_id':'INV-HIGH-001'},c)
    assert result.error=='permission_denied'
    assert c.audit_ledger.verify_integrity()

def test_browser_failure_is_audited():
    registry=ToolRegistry()
    registry.register(RegisteredTool('portal_read_invoice',PortalInvoiceInput,Permission.INVOICE_READ,lambda model,_ctx: (_ for _ in ()).throw(PortalAutomationError('portal down'))))
    c=ctx(); result=registry.execute_tool('portal_read_invoice',{'invoice_id':'INV-LOW-001'},c)
    assert not result.success and 'PortalAutomationError' in result.error
    assert c.audit_ledger.verify_integrity()
