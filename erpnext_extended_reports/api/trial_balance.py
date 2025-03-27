import json

from types import MethodType
import frappe
from frappe.database.query import QueryBuilder
from frappe.query_builder import (
    AliasedQuery,
    Criterion,
    CustomFunction,
    Table,
    Case,
    Query,
)
import frappe.query_builder
import frappe.query_builder.builder
from frappe.query_builder.functions import Sum, Count, Coalesce
from frappe.query_builder.terms import ParameterizedValueWrapper
from frappe.utils import get_table_name, getdate

from erpnext_extended_reports import utils


@frappe.whitelist(methods=["POST"])
def ext_trial_balance(filters: dict = {}):
    """gets trial balance

    Args:
        company (str): name of company
        hide_groups (bool, optional): include account groups if false.  Defaults to False.

    Returns:
        _type_: _description_
    """
    data = get_tb_data_version_one(filters)

    return data


def get_tb_data_version_one(
    filters: dict = {},
):
    """In this method, I tried to create tb without touching closing balance doctype

    Args:
        company (str): _description_
        hide_groups (bool, optional): _description_. Defaults to False.
    """
    group_filter = filters.get("group", {"hide_groups": False, "flat": False})
    hide_zero_accounts = filters.get("hide_zero_accounts", False)
    hide_groups = group_filter.get("hide_groups")
    company = filters.get("company")
    gl_entry = frappe.qb.DocType("GL Entry")
    account = frappe.qb.DocType("Account")
    gl_amount_fields = [
        Sum(Case().when(gl_entry.is_opening == "Yes", gl_entry.debit).else_(0)).as_(
            "opening_debits"
        ),
        Sum(Case().when(gl_entry.is_opening == "Yes", gl_entry.credit).else_(0)).as_(
            "opening_credits"
        ),
        Sum(Case().when(gl_entry.is_opening == "No", gl_entry.debit).else_(0)).as_(
            "debits"
        ),
        Sum(Case().when(gl_entry.is_opening == "No", gl_entry.credit).else_(0)).as_(
            "credits"
        ),
    ]
    amounts_query = (
        frappe.qb.from_(gl_entry)
        .select(gl_entry.account, *gl_amount_fields)
        .where(gl_entry.company == company)
    ).groupby(gl_entry.account)

    final_cte_query: QueryBuilder = frappe.qb.with_(amounts_query, "tb_non_grp")

    tb_non_grp_aliased_query = AliasedQuery("tb_non_grp")

    tb_grp_aliased_query = None

    if not hide_groups:
        final_cte_query = add_debit_credit_grps_query(
            final_cte_query, "tb_grp", company
        )
        tb_grp_aliased_query = AliasedQuery("tb_grp")

    final_cte_query = (
        final_cte_query.from_(account)
        .left_outer_join(tb_non_grp_aliased_query)
        .on(tb_non_grp_aliased_query.account == account.name)
        .where((account.company == company))
    )
    select_fields = [account.account_name.as_("name"), account.name.as_("id")]
    if hide_groups:
        final_cte_query = final_cte_query.where(account.is_group == 0)
        select_fields = select_fields + [
            Coalesce(
                tb_non_grp_aliased_query.opening_debits,
                0,
            ).as_("opening_debits"),
            Coalesce(
                tb_non_grp_aliased_query.opening_credits,
                0,
            ).as_("opening_credits"),
            Coalesce(
                tb_non_grp_aliased_query.debits,
                0,
            ).as_("debits"),
            Coalesce(
                tb_non_grp_aliased_query.credits,
                0,
            ).as_("credits"),
        ]
    else:
        final_cte_query = final_cte_query.left_outer_join(tb_grp_aliased_query).on(
            tb_grp_aliased_query.grp_name == account.name
        )
        select_fields = select_fields + [
            Coalesce(
                tb_grp_aliased_query.opening_debits,
                tb_non_grp_aliased_query.opening_debits,
                0,
            ).as_("opening_debits"),
            Coalesce(
                tb_grp_aliased_query.opening_credits,
                tb_non_grp_aliased_query.opening_credits,
                0,
            ).as_("opening_credits"),
            Coalesce(
                tb_grp_aliased_query.debits,
                tb_non_grp_aliased_query.debits,
                0,
            ).as_("debits"),
            Coalesce(
                tb_grp_aliased_query.credits,
                tb_non_grp_aliased_query.credits,
                0,
            ).as_("credits"),
        ]
    select_fields = select_fields + [
        account.parent_account,
        account.account_type,
        account.root_type,
        account.report_type,
    ]
    final_cte_query = final_cte_query.select(*select_fields)
    final_alias_query = AliasedQuery("combined_query")
    final_query = frappe.qb.from_(final_alias_query).select("*")

    with utils.QueryBuilderWithPatcher(final_query):
        final_query = final_query.patched_with_(final_cte_query, final_alias_query.name)
    if hide_zero_accounts:
        final_query = final_query.where(
            Criterion.all(
                [
                    (final_alias_query.opening_debits != 0),
                    (final_alias_query.opening_credits != 0),
                    (final_alias_query.debits != 0),
                    (final_alias_query.credits != 0),
                ]
            )
        )
    # to get support of recursive cte
    with utils.QueryBuilderWithSQLPatcher(final_query):
        # sql = final_query.get_sql()
        tb_data = final_query.run(as_dict=1)
        return tb_data


def add_debit_credit_grps_query(query: QueryBuilder, query_name, company):
    gl_entry = frappe.qb.DocType("GL Entry")
    account = frappe.qb.DocType("Account")

    accounts_query = account.select(
        account.parent_account.as_("grp_name"), account.name.as_("account_name")
    ).where((account.parent_account.notnull()) & (account.company == company))

    grp_accounts_query = account.as_("grp_accounts")

    account_hierarchy_alias_query = AliasedQuery("account_hierarchy")

    union_query = accounts_query * (
        frappe.qb.from_(account_hierarchy_alias_query)
        .join(grp_accounts_query)
        .on(grp_accounts_query.name == account_hierarchy_alias_query.grp_name)
        .select(
            grp_accounts_query.parent_account.as_("grp_name"),
            account_hierarchy_alias_query.account_name,
        )
        .where(
            (grp_accounts_query.parent_account.notnull())
            & (grp_accounts_query.company == company)
        )
    )
    # query.with_ = classmethod(utils.with_)

    # this patch is required ,
    # it will add WithQuery instead of alias query required for  QueryBuilderWithSQLPatcher
    with utils.QueryBuilderWithPatcher(query):
        query = query.patched_with_(union_query, "account_hierarchy", True)

    # account_hierarchy_alias_query = (
    #     frappe.qb.from_(grp_accounts_query)
    #     .join(account)
    #     .on(grp_accounts_query.name == account.parent_account)
    #     .select(grp_accounts_query.name.as_("grp_name"), account.name)
    # )
    tb_non_grp_query = AliasedQuery("tb_non_grp")
    debits_credits_grps_query = (
        frappe.qb.from_(tb_non_grp_query)
        .join(account_hierarchy_alias_query)
        .on(account_hierarchy_alias_query.account_name == tb_non_grp_query.account)
        .select(
            account_hierarchy_alias_query.grp_name,
            Sum(tb_non_grp_query.opening_debits).as_("opening_debits"),
            Sum(tb_non_grp_query.opening_credits).as_("opening_credits"),
            Sum(tb_non_grp_query.debits).as_("debits"),
            Sum(tb_non_grp_query.credits).as_("credits"),
        )
        .groupby(account_hierarchy_alias_query.grp_name)
    )
    query = query.with_(debits_credits_grps_query, query_name)
    return query
