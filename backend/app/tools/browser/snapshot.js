// Compact, model-friendly view of the current page.
// Tags every visible interactive element with data-op-ref so actions can target it by ref,
// and reports form metadata (method, action, field values) so policy can see what a submit
// would send. Password values are never read.
(maxElements) => {
  const visible = (el) => {
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0;
  };
  const text = (el) => (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
  const labelFor = (el) => {
    if (el.getAttribute("aria-label")) return el.getAttribute("aria-label");
    if (el.id) {
      const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (label) return text(label);
    }
    const wrapping = el.closest("label");
    if (wrapping) return text(wrapping);
    return el.getAttribute("placeholder") || el.getAttribute("name") || text(el) || el.getAttribute("value") || "";
  };

  document.querySelectorAll("[data-op-ref]").forEach((el) => el.removeAttribute("data-op-ref"));
  const forms = Array.from(document.forms);
  const selector = "a[href], button, input:not([type=hidden]), select, textarea, [role=button]";
  const elements = [];
  for (const el of document.querySelectorAll(selector)) {
    if (elements.length >= maxElements) break;
    if (!visible(el)) continue;
    const ref = `e${elements.length + 1}`;
    el.setAttribute("data-op-ref", ref);
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute("type") || (tag === "button" ? "submit" : "")).toLowerCase();
    const form = el.form || el.closest("form");
    const info = {
      ref, tag, type,
      label: labelFor(el).slice(0, 80),
      name: el.getAttribute("name") || "",
      form: form ? forms.indexOf(form) : -1,
      submits: !!form && (tag === "button" || tag === "input") && type === "submit",
    };
    if (tag === "a") info.href = el.href;
    if (tag === "select") {
      info.value = el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : "";
      info.options = Array.from(el.options).map((o) => o.text).slice(0, 40);
    } else if (tag === "input" || tag === "textarea") {
      info.value = type === "password" ? (el.value ? "••••" : "") : el.value;
    }
    elements.push(info);
  }

  const formInfo = forms.map((form, index) => {
    const fields = {};
    let hasPassword = false;
    for (const field of form.elements) {
      if (!field.name) continue;
      if (field.type === "password") { hasPassword = true; continue; }
      if (field.tagName.toLowerCase() === "select") {
        const option = field.options[field.selectedIndex];
        fields[field.name] = option ? option.value : "";
        if (option) fields[`${field.name}_label`] = option.text;
      } else if (field.type !== "submit" && field.type !== "button") {
        fields[field.name] = field.value;
      }
    }
    return {
      index,
      method: (form.getAttribute("method") || "get").toUpperCase(),
      action: new URL(form.getAttribute("action") || window.location.href, window.location.href).href,
      fields, has_password: hasPassword,
    };
  });

  const alerts = Array.from(document.querySelectorAll("[role=alert], [role=status], [aria-live]"))
    .filter(visible).map(text).filter(Boolean);
  const headings = Array.from(document.querySelectorAll("h1, h2, h3")).filter(visible).map(text);
  const tables = Array.from(document.querySelectorAll("table")).filter(visible).map((table) => ({
    label: table.getAttribute("aria-label") || "",
    rows: Array.from(table.rows).slice(0, 40).map((row) => Array.from(row.cells).map(text)),
  }));
  const main = document.querySelector("main") || document.body;
  return {
    url: window.location.href,
    title: document.title,
    alerts, headings, tables, elements,
    forms: formInfo,
    text: text(main).slice(0, 2500),
  };
}
