from erpnext.setup.doctype.company.company import Company
import frappe
import frappe.commands
import frappe.commands.utils
from frappe.tests.test_api import FrappeAPITestCase, generate_admin_keys
from erpnext_extended_reports.constants import *
from erpnext_extended_reports.api import get_trial_balance


import frappe.utils


class TrialBalanceTests(FrappeAPITestCase):

    def setUp(self):
        self.clean_up()
        self.create_test_company()
        return super().setUp()

    def tearDown(self):
        self.delete_test_company()
        # frappe.db.rollback(save_point="before_test")

    def test_empty_trial_balance(self):

        response = self.post(
            self.method(TRIAL_BALANCE_APINAME),
            {
                "filters": {"company": [self.company.name]},
                "sid": self.sid,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json
        length = len(data["message"])

        accounts_count = frappe.db.count(
            "Account", filters={"company": self.company.name}
        )
        self.assertEqual(length, accounts_count)

    def test_empty_trial_balance_when_grps_excluded(self):
        response_with_no_grps = self.post(
            self.method(TRIAL_BALANCE_APINAME),
            {
                "sid": self.sid,
                "filters": {
                    "company": [self.company.name],
                    "group": {"hide_groups": True},
                },
            },
        )
        self.assertEqual(
            len(response_with_no_grps.json["message"]),
            frappe.db.count(
                "Account", filters={"company": self.company.name, "is_group": 0}
            ),
        )

    def test_empty_trial_balance_when_zero_accounts_hidden(self):
        response_with_filtered = self.post(
            self.method(TRIAL_BALANCE_APINAME),
            {
                "sid": self.sid,
                "filters": {"company": [self.company.name], "hide_zero_accounts": True},
            },
        )
        self.assertEqual(len(response_with_filtered.json["message"]), 0)

    def test_trial_balance(self):
        self.company: Company = frappe.new_doc("Sales Invoice")
        response_with_filtered = self.post(
            self.method(TRIAL_BALANCE_APINAME),
            {
                "sid": self.sid,
                "filters": {"company": [self.company.name], "hide_zero_accounts": True},
            },
        )
        self.assertEqual(len(response_with_filtered.json["message"]), 0)

    def create_test_company(self, company_name="_Test TB Company", abbr="_TTC"):
        self.company: Company = frappe.new_doc("Company")
        self.company.company_name = company_name
        self.company.abbr = abbr
        self.company.chart_of_accounts = "Standard"
        self.company.create_chart_of_accounts_based_on = "Standard Template"
        self.company.default_currency = "INR"
        self.company = self.company.save()

    def delete_test_company(self, company_name="_Test TB Company", abbr="c"):
        self.company.delete()
        frappe.get_list("Account", fields=["account_name"], filters=[])

    def clean_up(self, company_name="_Test TB Company"):
        frappe.delete_doc("Company", company_name, ignore_permissions=True)
        # frappe.db.commit()
