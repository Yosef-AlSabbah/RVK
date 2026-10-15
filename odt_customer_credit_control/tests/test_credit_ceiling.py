# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""Monthly credit ceiling, customer cap and Finance Manager approval (REQ-022)."""

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import CreditControlCase


@tagged("post_install", "-at_install", "odt_customer_credit_control")
class TestCreditCeiling(CreditControlCase):
    """REQ-022 T1 to T10: totals, blocks at confirmation, approval and exposure."""

    def setUp(self):
        """Give Al Nakheel 420,000 SAR of October credit sales (cap 500,000)."""
        super().setUp()
        self.position = self.make_order(self.al_nakheel, 420_000)
        self.confirm_on(self.position, "2026-10-10 09:00:00")

    def test_req022_t1_blocks_over_cap(self):
        """A 90,000 SAR Net 30 order over the 500,000 cap waits for approval."""
        order = self.make_order(self.al_nakheel, 90_000)
        self.confirm_on(order, "2026-10-20 09:00:00")
        self.assertIn(order.state, ("draft", "sent"))
        self.assertEqual(order.credit_approval, "pending")

    def test_req022_t2_confirms_at_cap(self):
        """An 80,000 SAR order confirms, bringing Al Nakheel exactly to its cap."""
        order = self.make_order(self.al_nakheel, 80_000)
        self.confirm_on(order, "2026-10-20 09:00:00")
        self.assertEqual(order.state, "sale")
        self.assertEqual(
            self.exposure(self.al_nakheel, self.rvk, self.OCT).credit_sales, 500_000
        )

    def test_req022_t3_finance_approval_confirms(self):
        """The Finance Manager approves the blocked order with a reason; it confirms."""
        order = self.make_order(self.al_nakheel, 90_000)
        self.confirm_on(order, "2026-10-20 09:00:00")
        with self.assertRaises(AccessError):
            order.with_user(self.salesperson).action_credit_approve("Good customer")
        with self.freeze("2026-10-21 10:00:00"):
            order.with_user(self.finance_manager).action_credit_approve(
                "Strategic tender"
            )
        self.assertEqual(order.state, "sale")
        self.assertEqual(order.credit_approval, "approved")
        self.assertEqual(order.credit_approved_by_id, self.finance_manager)
        self.assertEqual(str(order.credit_approval_date), "2026-10-21 10:00:00")
        self.assertEqual(order.credit_approval_note, "Strategic tender")

    def test_req022_t4_advance_not_counted(self):
        """A 300,000 SAR order on 100% Advance confirms at the cap and is not counted."""
        top_up = self.make_order(self.al_nakheel, 80_000)
        self.confirm_on(top_up, "2026-10-15 09:00:00")
        order = self.make_order(self.al_nakheel, 300_000, term=self.advance)
        self.confirm_on(order, "2026-10-20 09:00:00")
        self.assertEqual(order.state, "sale")
        self.assertEqual(
            self.exposure(self.al_nakheel, self.rvk, self.OCT).credit_sales, 500_000
        )

    def test_req022_t5_excluded_special_lines(self):
        """Only 50,000 of a 120,000 order holding a 70,000 excluded special line counts."""
        before = self.company_total(self.rvk, self.OCT)
        order = self.make_order(
            self.al_nakheel,
            0,
            lines=[(self.product, 50_000), (self.special_product, 70_000)],
        )
        self.confirm_on(order, "2026-10-20 09:00:00")
        self.assertEqual(order.state, "sale")
        self.assertEqual(
            self.exposure(self.al_nakheel, self.rvk, self.OCT).credit_sales, 470_000
        )
        self.assertEqual(self.company_total(self.rvk, self.OCT) - before, 50_000)

    def test_req022_t6_new_month_restarts(self):
        """At its cap on 31 October, Al Nakheel confirms 90,000 on 1 November."""
        top_up = self.make_order(self.al_nakheel, 80_000)
        self.confirm_on(top_up, "2026-10-31 09:00:00")
        order = self.make_order(self.al_nakheel, 90_000)
        self.confirm_on(order, "2026-11-01 09:00:00")
        self.assertEqual(order.state, "sale")
        self.assertEqual(
            self.exposure(self.al_nakheel, self.rvk, self.NOV).credit_sales, 90_000
        )

    def _company_at(self, amount):
        """Bring RVK's October credit sales to the given amount through one big buyer."""
        missing = amount - self.company_total(self.rvk, self.OCT)
        order = self.make_order(self.big_buyer, missing)
        self.confirm_on(order, "2026-10-12 09:00:00")
        self.assertEqual(self.company_total(self.rvk, self.OCT), amount)

    def test_req022_t7_blocks_over_company_ceiling(self):
        """At 4,960,000, a 60,000 order within Gulf Pipes' own cap waits for approval."""
        self._company_at(4_960_000)
        order = self.make_order(self.gulf_pipes, 60_000)
        self.confirm_on(order, "2026-10-20 09:00:00")
        self.assertEqual(order.credit_approval, "pending")
        self.assertIn(order.state, ("draft", "sent"))

    def test_req022_t8_ceiling_boundary(self):
        """40,000 lands exactly on the ceiling and confirms; a further 1,000 waits."""
        self._company_at(4_960_000)
        first = self.make_order(self.gulf_pipes, 40_000)
        self.confirm_on(first, "2026-10-20 09:00:00")
        self.assertEqual(first.state, "sale")
        second = self.make_order(self.gulf_pipes, 1_000)
        self.confirm_on(second, "2026-10-20 10:00:00")
        self.assertEqual(second.credit_approval, "pending")

    def test_req022_t9_companies_apart(self):
        """Waterline's 1,500,000 of October sales are not in RVK's company total."""
        rvk_before = self.company_total(self.rvk, self.OCT)
        order = self.make_order(self.big_buyer, 1_500_000, company=self.waterline)
        self.confirm_on(order, "2026-10-15 09:00:00")
        self.assertEqual(order.state, "sale")
        self.assertEqual(self.company_total(self.rvk, self.OCT), rvk_before)
        self.assertEqual(self.company_total(self.waterline, self.OCT), 1_500_000)

    def test_req022_t10_exposure_share(self):
        """200,000 of October sales and a 10% cap show a 4% share beside the cap."""
        self.position.write({"state": "cancel"})
        order = self.make_order(self.al_nakheel, 200_000)
        self.confirm_on(order, "2026-10-20 09:00:00")
        line = self.exposure(self.al_nakheel, self.rvk, self.OCT)
        self.assertAlmostEqual(line.share_pct, 4.0)
        self.assertAlmostEqual(line.cap_pct, 10.0)
        self.assertAlmostEqual(line.credit_ceiling, 5_000_000)
        with self.freeze("2026-10-20 10:00:00"):
            quotation = self.make_order(self.al_nakheel, 1_000)
            self.assertAlmostEqual(quotation.credit_share_pct, 4.0)

    def test_rule_exposure_company(self):
        """A user of RVK only sees RVK exposure lines, none of Waterline's."""
        order = self.make_order(self.big_buyer, 1_500_000, company=self.waterline)
        self.confirm_on(order, "2026-10-15 09:00:00")
        self.env.flush_all()
        seen = self.env["credit.exposure"].with_user(self.rvk_user).search([])
        self.assertTrue(seen)
        self.assertEqual(seen.company_id, self.rvk)
