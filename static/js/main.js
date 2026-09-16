// INVEXA — client behaviour
(function () {
  "use strict";

  /* Theme toggle -------------------------------------------------- */
  const root = document.documentElement;
  const saved = localStorage.getItem("invexa-theme");
  if (saved) root.setAttribute("data-theme", saved);

  document.querySelectorAll("[data-theme-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const current = root.getAttribute("data-theme") === "light" ? "light" : "dark";
      const next = current === "light" ? "dark" : "light";
      root.setAttribute("data-theme", next);
      localStorage.setItem("invexa-theme", next);
    });
  });

  /* Mobile sidebar -------------------------------------------------- */
  const sidebar = document.querySelector(".sidebar");
  const backdrop = document.querySelector(".sidebar-backdrop");
  document.querySelectorAll("[data-menu-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      sidebar && sidebar.classList.toggle("open");
      backdrop && backdrop.classList.toggle("open");
    });
  });
  backdrop &&
    backdrop.addEventListener("click", () => {
      sidebar.classList.remove("open");
      backdrop.classList.remove("open");
    });

  /* Auto-dismiss toasts -------------------------------------------------- */
  document.querySelectorAll(".toast").forEach((toast) => {
    const close = () => {
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 200);
    };
    const btn = toast.querySelector("button");
    btn && btn.addEventListener("click", close);
    setTimeout(close, 4500);
  });

  /* Delete confirmation -------------------------------------------------- */
  document.querySelectorAll("[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (e) => {
      const msg = form.getAttribute("data-confirm") || "Are you sure?";
      if (!window.confirm(msg)) e.preventDefault();
    });
  });

  /* Live table search (client-side, for small lists) -------------------------------------------------- */
  document.querySelectorAll("[data-live-filter]").forEach((input) => {
    const targetSel = input.getAttribute("data-live-filter");
    const rows = () => document.querySelectorAll(targetSel);
    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      rows().forEach((row) => {
        const text = row.getAttribute("data-search") || row.textContent;
        row.style.display = text.toLowerCase().includes(q) ? "" : "none";
      });
    });
  });

  /* Create-sale live calculator -------------------------------------------------- */
  const productSelect = document.getElementById("product_id");
  const qtyInput = document.getElementById("quantity");
  const discountInput = document.getElementById("discount_percent");
  const summary = document.getElementById("pos-summary");

  function refreshPosSummary() {
    if (!productSelect || !summary) return;
    const opt = productSelect.options[productSelect.selectedIndex];
    const price = parseFloat((opt && opt.dataset.price) || 0);
    const stock = parseFloat((opt && opt.dataset.stock) || 0);
    const qty = Math.max(0, parseInt(qtyInput.value || "0", 10));
    const discountPct = Math.max(0, Math.min(100, parseFloat(discountInput.value || "0")));

    const subtotal = price * qty;
    const discountAmt = (subtotal * discountPct) / 100;
    const total = subtotal - discountAmt;

    document.getElementById("pos-unit-price").textContent = price.toFixed(2);
    document.getElementById("pos-subtotal").textContent = subtotal.toFixed(2);
    document.getElementById("pos-discount").textContent = discountAmt.toFixed(2);
    document.getElementById("pos-total").textContent = total.toFixed(2);

    const stockNote = document.getElementById("pos-stock-note");
    if (stockNote) {
      stockNote.textContent = opt && opt.value ? `${stock} unit(s) in stock` : "";
      stockNote.classList.toggle("text-faint", true);
    }

    const submitBtn = document.getElementById("pos-submit");
    if (submitBtn) submitBtn.disabled = !opt || !opt.value || qty <= 0 || qty > stock;
  }

  [productSelect, qtyInput, discountInput].forEach((el) => {
    el && el.addEventListener("input", refreshPosSummary);
    el && el.addEventListener("change", refreshPosSummary);
  });
  refreshPosSummary();

  const customerSelect = document.getElementById("customer_id");
  const newCustomerBlock = document.getElementById("new-customer-block");
  function toggleNewCustomer() {
    if (!customerSelect || !newCustomerBlock) return;
    newCustomerBlock.style.display = customerSelect.value === "new" ? "grid" : "none";
  }
  customerSelect && customerSelect.addEventListener("change", toggleNewCustomer);
  toggleNewCustomer();

  /* Charts -------------------------------------------------- */
  function withChart(fn) {
    if (window.Chart) fn(window.Chart);
  }

  const chartTextColor = getComputedStyle(document.body).getPropertyValue("--text-dim").trim() || "#9db3a9";
  const gridColor = "rgba(150,165,158,0.12)";
  Chart && (Chart.defaults.font.family = "Inter, sans-serif");
  Chart && (Chart.defaults.color = chartTextColor);

  const trendEl = document.getElementById("chart-trend");
  if (trendEl) {
    withChart((Chart) => {
      const gold = getComputedStyle(document.body).getPropertyValue("--gold").trim();
      new Chart(trendEl, {
        type: "line",
        data: {
          labels: JSON.parse(trendEl.dataset.labels),
          datasets: [
            {
              data: JSON.parse(trendEl.dataset.values),
              borderColor: gold,
              backgroundColor: "rgba(214,168,75,0.12)",
              fill: true,
              tension: 0.35,
              pointRadius: 0,
              pointHoverRadius: 4,
              borderWidth: 2,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { display: false }, ticks: { maxTicksLimit: 7, font: { size: 10 } } },
            y: { grid: { color: gridColor }, ticks: { font: { size: 10 } } },
          },
        },
      });
    });
  }

  const topEl = document.getElementById("chart-top-products");
  if (topEl) {
    withChart((Chart) => {
      const teal = getComputedStyle(document.body).getPropertyValue("--teal").trim();
      new Chart(topEl, {
        type: "bar",
        data: {
          labels: JSON.parse(topEl.dataset.labels),
          datasets: [{ data: JSON.parse(topEl.dataset.values), backgroundColor: teal, borderRadius: 5, maxBarThickness: 28 }],
        },
        options: {
          indexAxis: "y",
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { color: gridColor }, ticks: { font: { size: 10 } } },
            y: { grid: { display: false }, ticks: { font: { size: 11 } } },
          },
        },
      });
    });
  }

  const catEl = document.getElementById("chart-category-value");
  if (catEl) {
    withChart((Chart) => {
      const gold = getComputedStyle(document.body).getPropertyValue("--gold").trim();
      const teal = getComputedStyle(document.body).getPropertyValue("--teal").trim();
      const palette = [gold, teal, "#e2635a", "#9b8cd8", "#7bc67e", "#e0a76f"];
      new Chart(catEl, {
        type: "doughnut",
        data: {
          labels: JSON.parse(catEl.dataset.labels),
          datasets: [{ data: JSON.parse(catEl.dataset.values), backgroundColor: palette, borderWidth: 0 }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: "68%",
          plugins: { legend: { display: false } },
        },
      });
    });
  }

  /* Live table search -------------------------------------------------
     Any <input data-live-search="#tableId"> instantly filters the rows
     of the matching <table id="tableId"> as the user types — no reload,
     no waiting. Works from the 1st character typed. Used on Products,
     Categories, Sales, Stock and Customers. */
  document.querySelectorAll("[data-live-search]").forEach((input) => {
    const table = document.querySelector(input.getAttribute("data-live-search"));
    if (!table) return;
    const tbody = table.querySelector("tbody");
    if (!tbody) return;

    const rows = Array.from(tbody.querySelectorAll(":scope > tr"));
    const colCount = table.querySelectorAll("thead th").length || 10;

    const emptyRow = document.createElement("tr");
    emptyRow.className = "live-search-empty";
    emptyRow.style.display = "none";
    const emptyCell = document.createElement("td");
    emptyCell.colSpan = colCount;
    emptyCell.style.cssText = "text-align:center;color:var(--muted);padding:28px 12px;";
    emptyCell.textContent = "No matches for your search.";
    emptyRow.appendChild(emptyCell);
    tbody.appendChild(emptyRow);

    const runFilter = () => {
      const term = input.value.trim().toLowerCase();
      let visible = 0;
      rows.forEach((row) => {
        const match = term === "" || row.innerText.toLowerCase().includes(term);
        row.style.display = match ? "" : "none";
        if (match) visible++;
      });
      emptyRow.style.display = visible === 0 ? "" : "none";
    };

    input.addEventListener("input", runFilter);
    if (input.value) runFilter();
  });
})();
