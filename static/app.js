// Small helpers for the pages. The app works without this; it just makes forms nicer.
document.addEventListener("DOMContentLoaded", () => {
  // Property switcher in the header
  const sw = document.getElementById("switch");
  if (sw) sw.addEventListener("change", () => {
    location.href = "/switch?pid=" + sw.value + "&next=" + encodeURIComponent(location.pathname + location.search);
  });

  // Ask before deleting
  document.querySelectorAll("form[data-confirm]").forEach(f =>
    f.addEventListener("submit", e => { if (!confirm(f.dataset.confirm)) e.preventDefault(); }));

  // Add/edit money form: show the right fields for Expense vs Income
  const entry = document.getElementById("entry");
  if (entry) {
    const update = () => {
      const kind = entry.querySelector("input[name=kind]:checked").value;
      entry.querySelectorAll("[data-kind]").forEach(el => {
        const on = el.dataset.kind === kind;
        el.classList.toggle("hide", !on);
        el.querySelectorAll("select,input").forEach(i => i.disabled = !on);
      });
      const cat = entry.querySelector("select[name=category_expense]");
      const cap = document.getElementById("capital");
      if (cap) cap.classList.toggle("hide", kind !== "expense" || cat.value !== "Capital improvement");
      const esc = document.getElementById("escrow-opt");
      if (esc) esc.classList.toggle("hide", kind !== "expense" || !["Property taxes", "Insurance"].includes(cat.value));
      const hint = document.getElementById("cat-hint");
      const sel = entry.querySelector(`select[name=category_${kind}]`);
      if (hint && sel) hint.textContent = sel.selectedOptions[0]?.dataset.hint || "";
      const lease = entry.querySelector("select[name=lease_id]");
      const prop = document.getElementById("prop-field");
      if (prop && lease) prop.classList.toggle("hide", kind === "income" && !!lease.value);
    };
    entry.addEventListener("change", update);
    update();
    // Picking a tenant fills in rent as the category and the lease's rent as the amount
    const lease = entry.querySelector("select[name=lease_id]");
    if (lease) lease.addEventListener("change", () => {
      const o = lease.selectedOptions[0];
      const amt = entry.querySelector("input[name=amount]");
      if (o && o.dataset.rent && !amt.value) amt.value = o.dataset.rent;
      if (o && o.value) entry.querySelector("select[name=category_income]").value = "Rent";
      update();
    });
  }

  // Show the "Mark done" form for a maintenance task
  document.querySelectorAll("[data-toggle]").forEach(b => b.addEventListener("click", () => {
    const el = document.getElementById(b.dataset.toggle);
    el.classList.toggle("hide");
    const first = el.querySelector("input:not([type=hidden])");
    if (first && !el.classList.contains("hide")) first.focus();
  }));
});
