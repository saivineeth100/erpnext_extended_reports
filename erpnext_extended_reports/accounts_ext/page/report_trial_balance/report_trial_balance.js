frappe.pages['report-trial-balance'].on_page_load = function (wrapper) {
    frappe.report_tb = new TrialBalanceReport(wrapper);
    console.debug(frappe.report_tb);
};
class TrialBalanceReport {
    constructor(wrapper) {
        frappe.ui.make_app_page({
            parent: wrapper,
            title: __('Trial Balance'),
            single_column: true,
            card_layout: true,
        });
        this.parent = wrapper;
        this.page = this.parent.page;
        console.debug(this.page);
        this.$container = $(`<div class="trialbalance container">
			<div class="tb-title">Trial Balance</div>
			<div class="tb-content">Content</div>
		</div>`).appendTo(this.page.main);
    }
}
