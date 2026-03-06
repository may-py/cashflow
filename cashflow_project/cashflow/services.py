"""
services.py
~~~~~~~~~~~
Transforms raw Odoo AR/AP lines into:
  - Day-level buckets with THB amounts
  - Pivot table grouped by N-day periods (7=weekly, 30=monthly, etc.)
  - Running cumulative balance in THB
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class CashflowLine:
    line_id:    int
    entry_ref:  str
    partner:    str
    entry_date: date | None
    due_date:   date | None
    amount:     Decimal          # company currency (positive=inflow, negative=outflow)
    amount_thb: Decimal          # converted to THB
    currency:   str              # original invoice currency
    move_ref:   str
    line_type:  Literal['receivable', 'payable']
    company:    str
    company_id: int


@dataclass
class DayBucket:
    day:         date
    inflow:      Decimal = Decimal('0')
    outflow:     Decimal = Decimal('0')
    net:         Decimal = Decimal('0')
    running:     Decimal = Decimal('0')
    inflow_thb:  Decimal = Decimal('0')
    outflow_thb: Decimal = Decimal('0')
    net_thb:     Decimal = Decimal('0')
    running_thb: Decimal = Decimal('0')
    lines:       list[CashflowLine] = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.day.strftime('%d %b %Y')


@dataclass
class PivotPeriod:
    """A grouped period bucket for the pivot table."""
    period_label:  str
    date_from:     date
    date_to:       date
    inflow_thb:    Decimal = Decimal('0')
    outflow_thb:   Decimal = Decimal('0')
    net_thb:       Decimal = Decimal('0')
    running_thb:   Decimal = Decimal('0')
    lines:         list[CashflowLine] = field(default_factory=list)


@dataclass
class CashflowProjection:
    date_from:         date
    date_to:           date
    buckets:           list[DayBucket]
    total_inflow:      Decimal
    total_outflow:     Decimal
    net_position:      Decimal
    total_inflow_thb:  Decimal = Decimal('0')
    total_outflow_thb: Decimal = Decimal('0')
    net_position_thb:  Decimal = Decimal('0')
    opening_balance:   Decimal = Decimal('0')

    @property
    def closing_balance_thb(self) -> Decimal:
        """Opening balance + all inflows + all outflows (outflows are negative)."""
        return self.opening_balance + self.net_position_thb

    @property
    def chart_labels(self) -> list[str]:
        return [b.label for b in self.buckets if b.lines]

    @property
    def chart_inflows(self) -> list[float]:
        return [float(b.inflow_thb) for b in self.buckets if b.lines]

    @property
    def chart_outflows(self) -> list[float]:
        return [float(b.outflow_thb) for b in self.buckets if b.lines]

    @property
    def chart_running(self) -> list[float]:
        return [float(b.running_thb) for b in self.buckets if b.lines]

    def pivot(self, group_days: int = 7) -> list[PivotPeriod]:
        """Group day buckets into N-day periods for the pivot table."""
        if not self.buckets:
            return []
        periods: list[PivotPeriod] = []
        all_buckets = list(self.buckets)
        running = Decimal('0')
        idx = 0
        while idx < len(all_buckets):
            end = min(idx + group_days, len(all_buckets))
            chunk  = all_buckets[idx:end]
            d_from = chunk[0].day
            d_to   = chunk[-1].day
            label  = (f'{d_from.strftime("%d %b")} – {d_to.strftime("%d %b %Y")}'
                      if d_from != d_to else d_from.strftime('%d %b %Y'))
            pp = PivotPeriod(period_label=label, date_from=d_from, date_to=d_to)
            for b in chunk:
                pp.inflow_thb  += b.inflow_thb
                pp.outflow_thb += b.outflow_thb
                pp.net_thb     += b.net_thb
                pp.lines.extend(b.lines)
            running        += pp.net_thb
            pp.running_thb  = running
            periods.append(pp)
            idx = end
        return periods


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_date(val) -> date | None:
    if not val:
        return None
    if isinstance(val, date):
        return val
    try:
        return date.fromisoformat(str(val)[:10])
    except (ValueError, TypeError):
        return None

def _partner_name(f) -> str:
    return str(f[1]) if isinstance(f, (list, tuple)) and len(f) >= 2 else (str(f) if f else '—')

def _move_ref(f) -> str:
    return str(f[1]) if isinstance(f, (list, tuple)) and len(f) >= 2 else (str(f) if f else '—')

def _company_name(f) -> str:
    return str(f[1]) if isinstance(f, (list, tuple)) and len(f) >= 2 else ''

def _company_id(f) -> int:
    return int(f[0]) if isinstance(f, (list, tuple)) and len(f) >= 1 else 0

def _currency_name(f) -> str:
    return str(f[1]) if isinstance(f, (list, tuple)) and len(f) >= 2 else 'THB'


# ── Core builder ─────────────────────────────────────────────────────────────

def build_projection(raw: dict,
                     date_from: date,
                     date_to: date,
                     opening_balance: Decimal = Decimal('0')) -> CashflowProjection:
    """
    Build a CashflowProjection from raw Odoo data.

    THB conversion strategy:
      - amount_residual          = outstanding balance in COMPANY currency (THB for Thai companies)
      - amount_residual_currency = outstanding balance in ORIGINAL invoice currency
      - So amount_residual is already THB — use it directly as amount_thb.
      - currency_id shows the original invoice currency for display only.
    """
    lines: list[CashflowLine] = []

    for rec in raw.get('receivables', []):
        amount_thb  = Decimal(str(rec.get('amount_residual', 0)))         # already THB
        # amount_residual_currency is 0 when invoice currency = company currency (THB)
        _amt_cur    = Decimal(str(rec.get('amount_residual_currency') or 0))
        amount_orig = _amt_cur if _amt_cur != 0 else amount_thb
        currency    = _currency_name(rec.get('currency_id'))
        lines.append(CashflowLine(
            line_id    = rec['id'],
            entry_ref  = rec.get('name') or '—',
            partner    = _partner_name(rec.get('partner_id')),
            entry_date = _safe_date(rec.get('date')),
            due_date   = _safe_date(rec.get('date_maturity')) or _safe_date(rec.get('date')),
            amount     = amount_orig,      # original currency amount
            amount_thb = amount_thb,       # company currency = THB
            currency   = currency,
            move_ref   = _move_ref(rec.get('move_id')),
            line_type  = 'receivable',
            company    = _company_name(rec.get('company_id')),
            company_id = _company_id(rec.get('company_id')),
        ))

    for pay in raw.get('payables', []):
        # amount_residual is negative for payables in Odoo (credit side)
        # We take abs() then negate to represent outflow consistently
        amount_thb  = -abs(Decimal(str(pay.get('amount_residual', 0))))
        # amount_residual_currency is 0 when invoice currency = company currency (THB)
        # In that case fall back to amount_residual (already THB)
        _amt_cur    = Decimal(str(pay.get('amount_residual_currency') or 0))
        amount_orig = -abs(_amt_cur) if _amt_cur != 0 else amount_thb
        currency    = _currency_name(pay.get('currency_id'))
        lines.append(CashflowLine(
            line_id    = pay['id'],
            entry_ref  = pay.get('name') or '—',
            partner    = _partner_name(pay.get('partner_id')),
            entry_date = _safe_date(pay.get('date')),
            due_date   = _safe_date(pay.get('date_maturity')) or _safe_date(pay.get('date')),
            amount     = amount_orig,
            amount_thb = amount_thb,
            currency   = currency,
            move_ref   = _move_ref(pay.get('move_id')),
            line_type  = 'payable',
            company    = _company_name(pay.get('company_id')),
            company_id = _company_id(pay.get('company_id')),
        ))

    day_map: dict[date, DayBucket] = {}
    for i in range((date_to - date_from).days + 1):
        d = date_from + timedelta(days=i)
        day_map[d] = DayBucket(day=d)

    for line in lines:
        bd = line.due_date or date_from
        bd = max(date_from, min(date_to, bd))
        b  = day_map[bd]
        b.lines.append(line)
        # *** Route by amount_thb (always correctly signed), NOT amount_orig ***
        # amount_orig can be 0 for same-currency (THB) invoices, causing wrong bucket
        if line.amount_thb >= 0:
            b.inflow     += line.amount
            b.inflow_thb += line.amount_thb
        else:
            b.outflow     += line.amount
            b.outflow_thb += line.amount_thb
        b.net     += line.amount
        b.net_thb += line.amount_thb

    running = running_thb = opening_balance
    for d in sorted(day_map):
        b             = day_map[d]
        running      += b.net
        running_thb  += b.net_thb
        b.running     = running
        b.running_thb = running_thb

    buckets    = [day_map[d] for d in sorted(day_map)]
    ti         = sum((b.inflow      for b in buckets), Decimal('0'))
    to_        = sum((b.outflow     for b in buckets), Decimal('0'))
    ti_thb     = sum((b.inflow_thb  for b in buckets), Decimal('0'))
    to_thb     = sum((b.outflow_thb for b in buckets), Decimal('0'))

    return CashflowProjection(
        date_from         = date_from,
        date_to           = date_to,
        buckets           = buckets,
        total_inflow      = ti,
        total_outflow     = to_,
        net_position      = ti + to_,
        total_inflow_thb  = ti_thb,
        total_outflow_thb = to_thb,
        net_position_thb  = ti_thb + to_thb,
        opening_balance   = opening_balance,
    )