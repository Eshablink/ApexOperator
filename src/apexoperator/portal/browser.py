from pathlib import Path
from playwright.sync_api import Browser, Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

class PortalAutomationError(RuntimeError):
    pass

class LocalInvoicePortal:
    def __init__(self, browser: Browser, portal_html: str | Path, *, timeout_ms: int = 3000):
        self.browser = browser
        self.portal_html = Path(portal_html).resolve()
        self.timeout_ms = timeout_ms

    def _page(self):
        page = self.browser.new_page()
        page.set_default_timeout(self.timeout_ms)
        page.goto(self.portal_html.as_uri(), wait_until="domcontentloaded")
        return page

    @staticmethod
    def _first_visible(page, selectors: tuple[str, ...]):
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                if locator.is_visible():
                    return locator
            except PlaywrightError:
                pass
        return None

    def read_invoice(self, invoice_id: str) -> dict[str, str]:
        page = self._page()
        try:
            field = self._first_visible(page, ("#invoice-id", "[name='invoice_id']", "input[data-testid='invoice-id']"))
            button = self._first_visible(page, ("#search-invoice", "[data-testid='search-invoice']", "button[type='submit']"))
            if field is None or button is None:
                raise PortalAutomationError("invoice search controls not found")
            field.fill(invoice_id)
            button.click()
            page.wait_for_selector("#invoice-result, [data-testid='invoice-result'], .invoice-result", state="visible")
            status = page.locator("#invoice-status, [data-testid='invoice-status'], .invoice-status").inner_text().strip()
            total = page.locator("#invoice-total, [data-testid='invoice-total'], .invoice-total").inner_text().strip()
            return {"invoice_id": invoice_id, "status": status, "total": total}
        except (PlaywrightTimeoutError, PlaywrightError) as exc:
            raise PortalAutomationError(f"portal read failed: {type(exc).__name__}") from exc
        finally:
            page.close()

    def submit_invoice(self, invoice_id: str) -> dict[str, str]:
        page = self._page()
        try:
            field = self._first_visible(page, ("#invoice-id", "[name='invoice_id']", "input[data-testid='invoice-id']"))
            button = self._first_visible(page, ("#submit-invoice", "[data-testid='submit-invoice']", "button[data-action='submit']"))
            if field is None or button is None:
                raise PortalAutomationError("invoice submit controls not found")
            field.fill(invoice_id)
            button.click()
            page.wait_for_selector("#submission-result, [data-testid='submission-result'], .submission-result", state="visible")
            status = page.locator("#submission-status, [data-testid='submission-status'], .submission-status").inner_text().strip()
            if status.upper() != "SUBMITTED":
                raise PortalAutomationError(f"post-submit verification failed: status={status!r}")
            return {"invoice_id": invoice_id, "status": "SUBMITTED"}
        except PortalAutomationError:
            raise
        except (PlaywrightTimeoutError, PlaywrightError) as exc:
            raise PortalAutomationError(f"portal submit failed: {type(exc).__name__}") from exc
        finally:
            page.close()
