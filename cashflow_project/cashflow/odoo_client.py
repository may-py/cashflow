"""
odoo_client.py
~~~~~~~~~~~~~~
Thin wrapper around the Odoo 17/18 JSON-RPC API.

Odoo 17/18 hosted instances (e.g. https://example.com/odoo) still expose
the classic JSON-RPC endpoints at /web/session/authenticate and
/web/dataset/call_kw — but the base URL must NOT include a trailing /odoo
path segment, because the endpoints are always at the domain root.

  ODOO_URL = "https://odoo.com"   ← correct
  ODOO_URL = "https://odoo.com/odoo"  ← will 400

Authentication obtains a session cookie which is reused for all calls.
"""

import logging
from datetime import date
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class OdooAPIError(Exception):
    pass


class OdooClient:
    """Session-based JSON-RPC client for Odoo 17/18."""

    def __init__(self):
        # Strip any trailing /odoo or / so endpoints are always appended cleanly
        base = settings.ODOO_URL.rstrip('/')
        if base.endswith('/odoo'):
            base = base[:-5]          # remove the /odoo suffix
        self.base_url = base

        self.db       = settings.ODOO_DB
        self.username = settings.ODOO_USERNAME
        self.password = settings.ODOO_PASSWORD

        self._session = requests.Session()
        self._session.headers.update({
            'Content-Type': 'application/json',
        })

    # ── Authentication ────────────────────────────────────────────────────────

    def _authenticate(self) -> dict:
        """POST to /web/session/authenticate and store the session cookie."""
        url  = f'{self.base_url}/web/session/authenticate'
        body = {
            'jsonrpc': '2.0',
            'method':  'call',
            'id':      1,
            'params': {
                'db':       self.db,
                'login':    self.username,
                'password': self.password,
            },
        }
        logger.debug('Authenticating at %s', url)
        resp = self._session.post(url, json=body, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if data.get('error'):
            raise OdooAPIError(f"Auth failed: {data['error']}")

        result = data.get('result') or {}
        if not result.get('uid'):
            raise OdooAPIError(
                'Authentication returned no uid — check ODOO_USERNAME / ODOO_PASSWORD.'
            )
        logger.debug('Authenticated as uid=%s', result['uid'])
        return result

    # ── Low-level JSON-RPC call ───────────────────────────────────────────────

    def _call(self, model: str, method: str,
              args: list, kwargs: dict | None = None) -> Any:
        """Call model.method via /web/dataset/call_kw."""
        kwargs = kwargs or {}
        url    = f'{self.base_url}/web/dataset/call_kw'
        body   = {
            'jsonrpc': '2.0',
            'method':  'call',
            'id':      1,
            'params': {
                'model':  model,
                'method': method,
                'args':   args,
                'kwargs': kwargs,
            },
        }
        logger.debug('call_kw %s.%s → %s', model, method, url)
        resp = self._session.post(url, json=body, timeout=60)

        # If we get 400/401, try re-authenticating once then retry
        if resp.status_code in (400, 401):
            logger.warning('Got %s — re-authenticating...', resp.status_code)
            self._authenticate()
            resp = self._session.post(url, json=body, timeout=60)

        resp.raise_for_status()
        data = resp.json()

        if data.get('error'):
            err = data['error']
            # Session expired — re-auth once and retry
            if 'session' in str(err).lower() or 'access' in str(err).lower():
                logger.warning('Session error — re-authenticating...')
                self._authenticate()
                resp = self._session.post(url, json=body, timeout=60)
                resp.raise_for_status()
                data = resp.json()
            if data.get('error'):
                raise OdooAPIError(data['error'])

        return data.get('result')

    def _search_read(self, model: str, domain: list, fields: list,
                     order: str = '', limit: int = 0) -> list[dict]:
        kw: dict[str, Any] = {'fields': fields}
        if order:
            kw['order'] = order
        if limit:
            kw['limit'] = limit
        return self._call(model, 'search_read', [domain], kw) or []

    # ── Public data methods ───────────────────────────────────────────────────

    def get_companies(self) -> list[dict]:
        """Return companies with id in (1, 2)."""
        return self._search_read(
            'res.company',
            [('id', 'in', [1, 2])],
            fields=['id', 'name', 'currency_id'],
        )

    # Fields fetched for every move line
    _LINE_FIELDS = [
        'id', 'name', 'partner_id', 'date', 'date_maturity',
        'amount_residual', 'amount_residual_currency', 'currency_id',
        'move_id', 'company_id', 'company_currency_id', 'amount_currency',
        'account_id', 'display_type', 'full_reconcile_id',
    ]

    # Base domain shared by AR and AP — mirrors Odoo's aged report logic:
    #   - posted moves only
    #   - must have a partner (aged reports exclude partner-less lines)
    #   - exclude section/note display lines
    #   - unreconciled: use full_reconcile_id (replaces deprecated 'reconciled' in v17+)
    _BASE_DOMAIN = [
        ('parent_state',      '=',       'posted'),
        ('partner_id',        '!=',      False),
        ('display_type',      'not in',  ['line_section', 'line_note']),
        ('full_reconcile_id', '=',       False),
    ]

    def get_receivables(self, date_from: date | None = None,
                        date_to: date | None = None,
                        company_ids: list[int] | None = None) -> list[dict]:
        """Open AR lines — matches Odoo aged receivable report."""
        domain = self._BASE_DOMAIN + [
            ('account_id.account_type', '=', 'asset_receivable'),
            ('company_id', 'in', company_ids if company_ids else [1, 2]),
        ]
        # Date filter on date_maturity (due date), same as aged report
        if date_from:
            domain.append(('date_maturity', '>=', str(date_from)))
        if date_to:
            domain.append(('date_maturity', '<=', str(date_to)))

        return self._search_read(
            'account.move.line', domain,
            fields=self._LINE_FIELDS,
            order='date_maturity asc',
        )

    def get_payables(self, date_from: date | None = None,
                     date_to: date | None = None,
                     company_ids: list[int] | None = None) -> list[dict]:
        """Open AP lines — matches Odoo aged payable report."""
        domain = self._BASE_DOMAIN + [
            ('account_id.account_type', '=', 'liability_payable'),
            ('company_id', 'in', company_ids if company_ids else [1, 2]),
        ]
        if date_from:
            domain.append(('date_maturity', '>=', str(date_from)))
        if date_to:
            domain.append(('date_maturity', '<=', str(date_to)))

        return self._search_read(
            'account.move.line', domain,
            fields=self._LINE_FIELDS,
            order='date_maturity asc',
        )


# ── Module-level singleton + cache ────────────────────────────────────────────

_client: OdooClient | None = None


def get_client() -> OdooClient:
    global _client
    if _client is None:
        _client = OdooClient()
        _client._authenticate()
    return _client


def fetch_cashflow_data(date_from: date | None = None,
                        date_to: date | None = None,
                        company_ids: list[int] | None = None) -> dict:
    """
    Fetch AR + AP from Odoo.
    THB conversion uses amount_residual (already in company currency = THB)
    and amount_residual_currency (original invoice currency amount) from each line.
    No separate rate lookup needed.
    """
    ids_key   = ','.join(str(i) for i in sorted(company_ids)) if company_ids else '1,2'
    cache_key = f'odoo_cashflow_{date_from}_{date_to}_{ids_key}'
    cached    = cache.get(cache_key)
    if cached:
        return cached

    effective_ids = company_ids if company_ids else [1, 2]
    client        = get_client()
    receivables   = client.get_receivables(date_from, date_to, effective_ids)
    payables      = client.get_payables(date_from, date_to, effective_ids)
    companies     = client.get_companies()

    result = {
        'receivables': receivables,
        'payables':    payables,
        'companies':   companies,
    }
    cache.set(cache_key, result, timeout=settings.ODOO_CACHE_TIMEOUT)
    return result