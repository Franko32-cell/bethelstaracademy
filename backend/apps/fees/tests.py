from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import TestCase
from rest_framework.test import APIClient

from apps.classes.models import SchoolClass
from apps.fees.models import Fee, PaymentTransaction
from apps.students.models import Student


class FeeWhatsAppEndpointTests(TestCase):

	def setUp(self):
		self.user = get_user_model().objects.create_user(username="fee-test", password="pass")
		self.client = APIClient()
		self.client.force_authenticate(user=self.user)
		school_class = SchoolClass.objects.create(name="JSS 1", level="basic_7_9")
		self.student = Student.objects.create(
			user=self.user,
			admission_number="FEE001",
			first_name="Jane",
			last_name="Doe",
			parent_phone="0241234567",
			school_class=school_class,
		)
		self.fee = Fee.objects.create(
			student=self.student,
			term="term1",
			amount=Decimal("500.00"),
		)
		self.transaction = PaymentTransaction.objects.create(
			fee=self.fee,
			amount=Decimal("100.00"),
			recorded_by=self.user,
		)

	@patch("api.views.fee_whatsapp_view.send_whatsapp_bill")
	@patch("api.views.fee_whatsapp_view.StudentFeeBillPDFView.get")
	def test_send_bill_endpoint(self, build_pdf, send_bill):
		build_pdf.return_value = HttpResponse(b"pdf", content_type="application/pdf")
		send_bill.return_value = {"success": True, "reason": None, "message_id": "bill-1"}

		response = self.client.post(f"/api/fees/{self.fee.id}/send-whatsapp/")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["message_id"], "bill-1")
		self.assertEqual(send_bill.call_args.args[2], self.fee.total_amount)
		self.assertEqual(
			build_pdf.call_args.args[0].query_params["year"],
			str(self.fee.year),
		)

	@patch("api.views.fee_whatsapp_view.send_whatsapp_bill")
	@patch("api.views.fee_whatsapp_view.StudentFeeBillPDFView.get")
	def test_bulk_send_bills_scopes_fee_and_pdf_to_requested_year(self, build_pdf, send_bill):
		Fee.objects.create(
			student=self.student,
			term=self.fee.term,
			year=self.fee.year - 1,
			amount=Decimal("700.00"),
		)
		build_pdf.return_value = HttpResponse(b"pdf", content_type="application/pdf")
		send_bill.return_value = {"success": True, "reason": None, "message_id": "bill-1"}

		response = self.client.post(
			"/api/fees/send-whatsapp/bulk/",
			{
				"school_class": self.student.school_class_id,
				"term": self.fee.term,
				"year": self.fee.year,
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(response.json()["sent"]), 1)
		self.assertEqual(build_pdf.call_count, 1)
		self.assertEqual(
			build_pdf.call_args.args[0].query_params["year"],
			str(self.fee.year),
		)

	@patch("api.views.fee_whatsapp_view.send_whatsapp_receipt")
	@patch("api.views.fee_whatsapp_view.PaymentReceiptPDFView.get")
	def test_send_receipt_endpoint(self, build_pdf, send_receipt):
		build_pdf.return_value = HttpResponse(b"pdf", content_type="application/pdf")
		send_receipt.return_value = {"success": True, "reason": None, "message_id": "receipt-1"}

		response = self.client.post(
			f"/api/fees/receipts/{self.transaction.id}/send-whatsapp/"
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["message_id"], "receipt-1")
		self.assertEqual(send_receipt.call_args.args[2], self.transaction.amount)

	def test_correct_payment_updates_fee_balance_and_links_replacement(self):
		response = self.client.post(
			f"/api/fees/{self.fee.id}/correct-payment/",
			{
				"transaction_id": self.transaction.id,
				"reason": "typed amount was wrong",
				"amount": "200.00",
			},
		)

		self.assertEqual(response.status_code, 200)
		replacement_id = response.data["transaction_id"]
		self.assertIsNotNone(replacement_id)

		self.fee.refresh_from_db()
		self.assertEqual(self.fee.paid, Decimal("200.00"))
		self.assertEqual(self.fee.balance, Decimal("300.00"))

		original = PaymentTransaction.objects.get(pk=self.transaction.id)
		self.assertTrue(original.is_void)
		self.assertEqual(original.replaced_by_id, replacement_id)

	def test_transactions_by_date_ignores_voided_amounts_when_printing_balance(self):
		response = self.client.post(
			f"/api/fees/{self.fee.id}/correct-payment/",
			{
				"transaction_id": self.transaction.id,
				"reason": "typed amount was wrong",
				"amount": "200.00",
			},
		)

		self.assertEqual(response.status_code, 200)
		replacement_id = response.data["transaction_id"]

		payload = self.client.get(
			"/api/fees/transactions/",
			{"date": self.transaction.created_at.strftime("%Y-%m-%d")},
		).json()
		items = {entry["id"]: entry for entry in payload}

		self.assertIn(replacement_id, items)
		self.assertEqual(items[replacement_id]["balance"], "300.00")
