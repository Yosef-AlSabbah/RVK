# Part of OdooTec. See LICENSE file for full copyright and licensing details.

"""
The overridden standard method, with a negative, a normal and a
standard-preserved test (O1 sale.order.action_quotation_send).
"""

from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import QuotationTermsCase


@tagged("post_install", "-at_install", "odt_quotation_payment_terms")
class TestOverrides(QuotationTermsCase):
    """O1."""

    def test_o1_negative_no_term_refused(self):
        """A quotation with no payment term is refused, naming the missing term."""
        order = self.make_quotation(self.al_nakheel, term=False)
        with self.assertRaisesRegex(UserError, "no payment term"):
            order.with_user(self.salesperson).action_quotation_send()

    def test_o1_normal_default_term_opens_composer(self):
        """A quotation on the customer's default term opens the email composer."""
        order = self.make_quotation(self.al_nakheel)
        self.assertEqual(order.payment_term_id, self.net30)
        action = order.with_user(self.salesperson).action_quotation_send()
        self.assertEqual(action["res_model"], "mail.compose.message")
        self.assertEqual(action["context"]["default_res_ids"], order.ids)

    def test_o1_standard_preserved_template_unchanged(self):
        """
        A quotation on an approved instalment term is sent exactly as standard.

        The standard quotation template and its attachment are used, and the
        instalment term still gives one due line per milestone on the invoice
        (REQ-024-T-FR5 is standard Odoo).
        """
        order = self.make_quotation(self.national_water)
        self.assertEqual(order.payment_term_id, self.milestones)
        action = self.send(order)
        template = self.env.ref("sale.email_template_edi_sale")
        self.assertEqual(action["context"]["default_template_id"], template.id)
        self.assertTrue(action["context"]["mark_so_as_sent"])
        self.assertEqual(action["context"]["default_composition_mode"], "comment")
        self.assertEqual(order.state, "sent")
        message = order.message_ids.filtered(lambda m: m.message_type == "comment")[:1]
        self.assertTrue(message, "no email was posted on the quotation")
        self.assertTrue(message.attachment_ids, "the quotation was not attached")

        order.action_confirm()
        invoice = order._create_invoices()
        invoice.invoice_date = date(2026, 10, 15)
        due_lines = invoice.line_ids.filtered(
            lambda line: line.display_type == "payment_term"
        )
        self.assertEqual(
            sorted(due_lines.mapped("date_maturity")),
            [date(2026, 10, 15), date(2026, 12, 14), date(2027, 2, 12)],
        )
