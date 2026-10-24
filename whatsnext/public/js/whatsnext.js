// Desk integration: a "WhatsApp" button on common ERPNext forms that sends an
// approved template to the document's customer/contact (optionally with the
// document's PDF as the header) and links to the chat in the Whatsnext app.
(function () {
	const DOCTYPES = [
		"Customer", "Contact", "Lead", "Supplier", "Opportunity", "Quotation",
		"Sales Order", "Sales Invoice", "Delivery Note", "Payment Entry",
		"Purchase Order", "Purchase Invoice", "Issue", "Employee", "CRM Lead",
	];
	const MAX_VARS = 10;
	const API = "whatsnext.whatsnext.api";

	function canUse() {
		return frappe.user.has_role("Whatsnext User") || frappe.user.has_role("System Manager");
	}

	function placeholders(text) {
		const nums = [...(text || "").matchAll(/\{\{(\d+)\}\}/g)].map((m) => parseInt(m[1], 10));
		return nums.length ? Math.max(...nums) : 0;
	}

	async function openDialog(frm) {
		const ctx = (await frappe.call(`${API}.get_document_whatsapp_context`, {
			doctype: frm.doctype,
			name: frm.doc.name,
		})).message || {};
		const templates = (await frappe.call(`${API}.get_templates`, { approved_only: 1 })).message || [];
		if (!templates.length) {
			frappe.msgprint(__("No approved WhatsApp templates yet. Create or sync them in the Whatsnext app."));
			return;
		}
		const byName = Object.fromEntries(templates.map((t) => [t.name, t]));

		const varFields = [];
		for (let i = 1; i <= MAX_VARS; i++) {
			varFields.push({ fieldname: `var_${i}`, fieldtype: "Data", label: __("Variable {0}", [i]), hidden: 1 });
		}

		const d = new frappe.ui.Dialog({
			title: __("Send WhatsApp"),
			fields: [
				{ fieldname: "to", fieldtype: "Data", label: __("WhatsApp Number"), reqd: 1, default: ctx.number || "" },
				{
					fieldname: "template", fieldtype: "Select", label: __("Template"), reqd: 1,
					options: [""].concat(templates.map((t) => t.name)),
					onchange: () => refresh(),
				},
				{ fieldname: "preview", fieldtype: "HTML" },
				{ fieldname: "header_1", fieldtype: "Data", label: __("Header Variable"), hidden: 1 },
				...varFields,
				{ fieldname: "attach_print", fieldtype: "Check", label: __("Attach this document as PDF"), hidden: 1, onchange: () => refresh() },
				{
					fieldname: "print_format", fieldtype: "Select", label: __("Print Format"), hidden: 1,
					options: [""].concat(ctx.print_formats || []), default: ctx.default_print_format || "",
				},
				{ fieldname: "header_media_url", fieldtype: "Data", label: __("Header Media URL"), hidden: 1 },
			],
			primary_action_label: __("Send"),
			primary_action: send,
			secondary_action_label: ctx.has_chat ? __("Open Chat") : null,
			secondary_action: ctx.has_chat ? () => window.open(`/whatsnext?conversation=${encodeURIComponent(ctx.conversation_id)}`, "_blank") : null,
		});

		let lastTemplate = null;
		function refresh() {
			const t = byName[d.get_value("template")];
			const count = t ? placeholders(t.body) : 0;
			for (let i = 1; i <= MAX_VARS; i++) d.set_df_property(`var_${i}`, "hidden", i > count ? 1 : 0);
			d.set_df_property("header_1", "hidden", t && t.header_type === "Text" && (t.header_text || "").includes("{{1}}") ? 0 : 1);

			const isDoc = t && t.header_type === "Document";
			const isMedia = t && ["Image", "Video", "Document"].includes(t.header_type);
			d.set_df_property("attach_print", "hidden", isDoc ? 0 : 1);
			// Default to attaching the document's PDF the first time a Document-header template is picked.
			if (t && t.name !== lastTemplate) {
				lastTemplate = t.name;
				if (isDoc && !d.get_value("attach_print")) { d.set_value("attach_print", 1); return; }
			}
			const attaching = isDoc && d.get_value("attach_print");
			d.set_df_property("print_format", "hidden", attaching ? 0 : 1);
			d.set_df_property("header_media_url", "hidden", isMedia && !attaching ? 0 : 1);
			if (isMedia && !attaching && !d.get_value("header_media_url") && t.header_example_url) {
				d.set_value("header_media_url", t.header_example_url);
			}
			d.fields_dict.preview.$wrapper.html(
				t ? `<div class="text-muted small" style="white-space:pre-wrap;margin-bottom:8px">${frappe.utils.escape_html(t.body || "")}</div>` : ""
			);
		}

		async function send() {
			const v = d.get_values();
			if (!v) return;
			const t = byName[v.template];
			const params = {};
			for (let i = 1; i <= placeholders(t.body); i++) params[String(i)] = v[`var_${i}`] || "";
			if (v.header_1) params.header_1 = v.header_1;

			d.disable_primary_action();
			try {
				const r = await frappe.call({
					method: `${API}.send_template_message`,
					args: {
						to: v.to,
						template: v.template,
						parameters: params,
						reference_doctype: frm.doctype,
						reference_name: frm.doc.name,
						header_media_url: v.attach_print ? null : v.header_media_url,
						attach_print: v.attach_print ? 1 : 0,
						print_format: v.print_format,
					},
					freeze: true,
					freeze_message: __("Sending..."),
				});
				const msg = r.message || {};
				d.hide();
				if (msg.status === "Failed") {
					frappe.msgprint({ title: __("WhatsApp not sent"), indicator: "red", message: frappe.utils.escape_html(msg.error_message || "") });
				} else {
					frappe.show_alert({ message: __("WhatsApp sent to {0}", [msg.to_number]), indicator: "green" });
				}
			} finally {
				d.enable_primary_action();
			}
		}

		d.show();
		refresh();
	}

	DOCTYPES.forEach((doctype) => {
		frappe.ui.form.on(doctype, {
			refresh(frm) {
				if (frm.is_new() || !canUse()) return;
				frm.add_custom_button(__("WhatsApp"), () => openDialog(frm), __("Send"));
			},
		});
	});
})();
