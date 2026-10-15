"use strict";
const $ = (s) => document.querySelector(s),
  esc = (s) =>
    String(s).replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
const money = (c) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    c / 100,
  );
const date = (t) =>
  new Date(t * 1000).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
const cents = (v) => {
  if (!/^\d+(\.\d{1,2})?$/.test(String(v)))
    throw new Error("Use an amount with at most two decimal places");
  return Math.round(Number(v) * 100);
};
let csrf = "",
  products = [],
  category = "All",
  bag = new Map(),
  desk = null,
  pendingCheckout = null,
  orderToken = "",
  isBusy = false;
const isAdmin = document.body.dataset.page === "admin";
async function api(path, body, token = "") {
  const headers = {};
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    headers["X-CSRF-Token"] = csrf;
  }
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || "Request failed");
    error.status = response.status;
    throw error;
  }
  return data;
}
function notice(message, error = false) {
  const el = $(isAdmin ? "#admin-notice" : "#shop-notice");
  el.textContent = message;
  el.classList.toggle("error", error);
  el.hidden = false;
}
function modal(html) {
  $("#modal-body").innerHTML = html;
  if (!$("#modal").open) $("#modal").showModal();
}
$("#close-modal").addEventListener("click", () => $("#modal").close());
function art(kind) {
  const shapes = {
    cup: '<path d="M62 93h95v78c0 32-95 32-95 0z" fill="url(#clay)"/><ellipse cx="109.5" cy="93" rx="47.5" ry="13" fill="#a65f43"/><ellipse cx="109.5" cy="93" rx="38" ry="8" fill="#6d4632"/><path d="M157 109c43-8 48 55 1 49" fill="none" stroke="#bd7957" stroke-width="18"/>',
    lamp: '<path d="M80 190h80l9 13H71z" fill="#8e5d3d"/><path d="M111 103h18v89h-18z" fill="url(#clay)"/><path d="M37 112c0-59 36-97 83-97s83 38 83 97z" fill="url(#clay)"/><ellipse cx="120" cy="112" rx="83" ry="9" fill="#8d5938"/>',
    vase: '<path d="M96 50h48l-3 51c35 33 45 58 38 79-8 26-108 26-116 0-7-21 3-46 36-79z" fill="url(#sand)"/><ellipse cx="120" cy="50" rx="24" ry="7" fill="#a69878"/>',
    carafe:
      '<path d="M99 35h44l-8 44c1 17 34 31 36 59l-2 47c-2 24-103 24-105 0l-2-47c2-28 35-42 36-59z" fill="url(#sage)"/><ellipse cx="121" cy="35" rx="23" ry="7" fill="#748267"/>',
    bowl: '<ellipse cx="120" cy="123" rx="89" ry="30" fill="#c3b38e"/><path d="M31 123c15 100 163 100 178 0-15 38-163 38-178 0" fill="url(#sand)"/><ellipse cx="120" cy="123" rx="77" ry="23" fill="#dfcfac"/>',
    tray: '<path d="M34 101l117-49 65 69-117 63z" fill="#b68a55"/><path d="M34 101v14l65 82 117-63v-13l-117 63z" fill="#947044"/><path d="M49 104l100-41 50 55-97 51z" fill="#c5a16f"/><path d="M67 110l100-24M79 128l101-25M91 144l99-26" stroke="#a98350" opacity=".3"/>',
  };
  return `<svg viewBox="0 0 240 240" aria-hidden="true"><defs><linearGradient id="clay"><stop stop-color="#aa6948"/><stop offset=".5" stop-color="#d09a72"/><stop offset="1" stop-color="#a56c4b"/></linearGradient><linearGradient id="sand"><stop stop-color="#baa780"/><stop offset=".5" stop-color="#e4d6b6"/><stop offset="1" stop-color="#b3a37f"/></linearGradient><linearGradient id="sage"><stop stop-color="#829074"/><stop offset=".5" stop-color="#bbc3a4"/><stop offset="1" stop-color="#7c8d6a"/></linearGradient></defs><ellipse cx="120" cy="206" rx="75" ry="8" fill="#65543b" opacity=".12"/>${shapes[kind] || shapes.vase}</svg>`;
}
function saveBag() {
  sessionStorage.setItem("reserve-cart.bag", JSON.stringify([...bag]));
  $("#bag-count").textContent = [...bag.values()].reduce((a, b) => a + b, 0);
}
async function loadCatalog() {
  const data = await api("/api/products");
  products = data.products;
  renderProducts();
}
function renderProducts() {
  const cats = ["All", ...new Set(products.map((p) => p.category))];
  $("#filters").innerHTML = cats
    .map(
      (c) =>
        `<button data-category="${esc(c)}" class="${category === c ? "active" : ""}">${esc(c)}</button>`,
    )
    .join("");
  const query = $("#search").value.toLowerCase();
  const matches = products.filter(
    (p) =>
      (category === "All" || p.category === category) &&
      `${p.name} ${p.description}`.toLowerCase().includes(query),
  );
  $(".section-title h2 span").textContent =
    ` (${String(products.length).padStart(2, "0")})`;
  $("#product-grid").innerHTML =
    matches
      .map(
        (p, index) =>
          `<article class="product-card"><button class="product-art" data-detail="${p.id}" aria-label="View ${esc(p.name)}">${art(p.art)}<span class="edition">STILLDAY / ${String(p.id).padStart(2, "0")}</span><span class="stock-label">${p.stock ? `${p.stock} available` : "Currently reserved"}</span></button><div class="product-info"><div><h3>${esc(p.name)}</h3><p>${esc(p.category)} · Small collection</p></div><strong>${money(p.price_cents)}</strong></div><div class="product-actions"><button data-detail="${p.id}">A closer look ↗</button><button class="add" data-add="${p.id}" ${p.stock ? "" : "disabled"}>Add to bag +</button></div></article>`,
      )
      .join("") || '<p class="empty">No objects match your search.</p>';
}
function changeBag(id, delta) {
  if (pendingCheckout) {
    notice("Resolve your pending reservation before changing the bag.", true);
    return;
  }
  const p = products.find((p) => p.id === id);
  if (!p) return;
  const qty = (bag.get(id) || 0) + delta;
  if (qty > Math.min(p.stock, 20)) {
    notice("That quantity is not currently available.", true);
    return;
  }
  if (qty <= 0) bag.delete(id);
  else bag.set(id, qty);
  saveBag();
}
function total() {
  return [...bag].reduce(
    (sum, [id, q]) =>
      sum + (products.find((p) => p.id === id)?.price_cents || 0) * q,
    0,
  );
}
function showBag() {
  const rows = [...bag]
    .map(([id, qty]) => {
      const p = products.find((p) => p.id === id);
      return p
        ? `<div class="bag-line"><div><strong>${esc(p.name)}</strong><small>${money(p.price_cents)} each</small></div><div class="quantity"><button data-bag-qty="${id}" data-delta="-1" aria-label="Remove one ${esc(p.name)}">−</button><span>${qty}</span><button data-bag-qty="${id}" data-delta="1" aria-label="Add one ${esc(p.name)}">+</button></div></div>`
        : `<div class="bag-line"><strong>Product #${id} is no longer available</strong><button data-remove="${id}">Remove</button></div>`;
    })
    .join("");
  modal(
    `<p class="eyebrow">A FEW GOOD THINGS</p><h2>Your bag.</h2>${bag.size ? rows : '<p class="empty">A little room for something lovely.</p>'}${bag.size ? `<div class="bag-total"><span>Total</span><strong>${money(total())}</strong></div><p>Local pickup. Prices are as listed. No shipping charges. Your items are held only after checkout.</p><button id="begin-checkout" class="dark-button">${pendingCheckout ? "Resume reservation" : "Reserve these objects"} →</button>` : ""}`,
  );
}
function showCheckout() {
  modal(
    `<p class="eyebrow">ONE LAST LITTLE STEP</p><h2>Make them yours.</h2><p>We’ll hold the available items for 30 minutes. Arrange payment directly with the shop before your reservation expires.</p><form id="checkout-form"><label>Your name<input name="name" required maxlength="100" autocomplete="name"></label><label>Email<input name="email" type="email" required maxlength="200" autocomplete="email"></label><label>Pickup note (optional)<textarea name="note" maxlength="400"></textarea></label><p>No payment is collected here. No automatic email is sent; save your private order link on the next screen.</p><div class="bag-total"><span>Reservation total</span><strong>${money(total())}</strong></div><div class="form-error" id="checkout-error" role="alert"></div><button class="dark-button" type="submit">Confirm reservation →</button></form>`,
  );
  if (pendingCheckout) {
    for (const name of ["name", "email", "note"])
      $("#checkout-form").elements[name].value = pendingCheckout[name];
  }
  $("#checkout-form").addEventListener("submit", submitCheckout);
}
async function submitCheckout(event) {
  event.preventDefault();
  if (isBusy) return;
  const form = event.currentTarget;
  try {
    if (!pendingCheckout) {
      const values = Object.fromEntries(new FormData(form));
      pendingCheckout = {
        ...values,
        idempotency_key: crypto.randomUUID(),
        items: [...bag].map(([product_id, quantity]) => ({
          product_id,
          quantity,
        })),
      };
      sessionStorage.setItem(
        "reserve-cart.pending",
        JSON.stringify(pendingCheckout),
      );
    }
    isBusy = true;
    form.querySelector("button").disabled = true;
    const result = await api("/api/checkout", pendingCheckout);
    bag.clear();
    pendingCheckout = null;
    sessionStorage.removeItem("reserve-cart.pending");
    saveBag();
    orderToken = result.token;
    sessionStorage.setItem("reserve-cart.last-order", orderToken);
    history.replaceState(null, "", `#order=${encodeURIComponent(orderToken)}`);
    await loadCatalog();
    renderOrder(result);
  } catch (error) {
    if (error.status && error.status < 500) {
      pendingCheckout = null;
      sessionStorage.removeItem("reserve-cart.pending");
    }
    $("#checkout-error").textContent =
      error.message +
      (pendingCheckout
        ? " Retry without changing the form to recover the same reservation."
        : "");
    form.querySelector("button").disabled = false;
  } finally {
    isBusy = false;
  }
}
function renderOrder(order) {
  const messages = {
    reserved: `Reserved until ${date(order.expires_at)}. Arrange payment with the shop before then.`,
    paid: "Payment recorded. Your objects are being prepared.",
    ready: "Ready for pickup. Confirm the pickup location with the shop.",
    collected: "Collected. Thank you for making room for a few good things.",
    cancelled: "Reservation cancelled. Your items have been released.",
    expired: "The reservation window ended. Your items have been released.",
    refunded: "The shop recorded an external refund and released the items.",
  };
  const link = `${location.origin}/#order=${encodeURIComponent(orderToken)}`;
  modal(
    `<p class="eyebrow">YOUR PRIVATE ORDER PAGE</p><h2>${order.status === "reserved" ? "A little something, held for you." : "Your collection."}</h2><p class="order-number">ORDER #${String(order.id).padStart(5, "0")} <span class="status ${order.status}">${order.status}</span></p><p>${messages[order.status]}</p><div class="order-items">${order.items.map((i) => `<div><span>${i.quantity} × ${esc(i.name)}</span><strong>${money(i.quantity * i.unit_cents)}</strong></div>`).join("")}</div><div class="bag-total"><span>Total</span><strong>${money(order.total_cents)}</strong></div><div class="order-link">${esc(link)}</div><p>Keep this link private. Anyone with it can view this order and cancel an unpaid reservation.</p><button id="copy-order" class="outline-button">Copy private link</button> <button id="refresh-order" class="outline-button">Refresh status</button>${order.status === "reserved" ? '<button id="cancel-order" class="dark-button">Cancel reservation</button>' : ""}<div class="timeline">${order.timeline.map((e) => `<div><span>${esc(e.action)}</span><time>${date(e.created_at)}</time></div>`).join("")}</div><div class="form-error" id="order-error" role="alert"></div>`,
  );
}
async function showOrder(token) {
  try {
    orderToken = token;
    renderOrder(await api("/api/order", undefined, token));
  } catch (error) {
    notice(error.message, true);
  }
}
function formModal(title, description, fields, submit, onSubmit) {
  modal(
    `<p class="eyebrow">THE SHOP DESK</p><h2>${title}</h2><p>${description}</p><form id="desk-form">${fields}<div id="form-error" class="form-error" role="alert"></div><button class="dark-button">${submit}</button></form>`,
  );
  $("#desk-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget,
      button = form.querySelector("button");
    button.disabled = true;
    try {
      await onSubmit(new FormData(form));
      $("#modal").close();
      await refreshDesk();
    } catch (error) {
      $("#form-error").textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
}
async function refreshDesk() {
  desk = await api("/api/admin/state");
  renderDesk();
}
function renderDesk() {
  const orders = desk.orders;
  $("#admin-stats").innerHTML = [
    [
      "Active reservations",
      orders.filter((o) => o.status === "reserved").length,
    ],
    ["Ready for pickup", orders.filter((o) => o.status === "ready").length],
    [
      "Paid total (latest 100)",
      money(
        orders
          .filter((o) => ["paid", "ready", "collected"].includes(o.status))
          .reduce((a, o) => a + o.total_cents, 0),
      ),
    ],
  ]
    .map(
      ([l, v]) =>
        `<div class="stat"><small>${l}</small><strong>${v}</strong></div>`,
    )
    .join("");
  const filter = $("#status-filter").value;
  $("#orders-body").innerHTML =
    orders
      .filter((o) => filter === "all" || o.status === filter)
      .map(
        (o) =>
          `<tr><td><strong>#${String(o.id).padStart(5, "0")}</strong><small>${date(o.created_at)}</small></td><td>${esc(o.customer_name)}<small>${esc(o.email)}</small></td><td><span class="status ${o.status}">${o.status}</span></td><td>${money(o.total_cents)}</td><td><button data-order="${o.id}">Review order →</button></td></tr>`,
      )
      .join("") ||
    '<tr><td colspan="5" class="empty">No orders in this view.</td></tr>';
  $("#inventory-body").innerHTML = desk.products
    .map(
      (p) =>
        `<tr><td>${esc(p.name)}<small>${esc(p.sku)}${p.active ? "" : " · Archived"}</small></td><td>${esc(p.category)}</td><td>${money(p.price_cents)}</td><td>${p.stock}</td><td><button data-edit="${p.id}">Edit</button><button data-stock="${p.id}">Stock</button></td></tr>`,
    )
    .join("");
}
function reviewOrder(id) {
  const o = desk.orders.find((o) => o.id === id);
  const actions =
    {
      reserved: [
        ["pay", "Record payment"],
        ["cancel", "Cancel hold"],
      ],
      paid: [
        ["ready", "Mark ready"],
        ["refund", "Record refund"],
      ],
      ready: [
        ["collect", "Mark collected"],
        ["refund", "Record refund"],
      ],
    }[o.status] || [];
  modal(
    `<p class="eyebrow">ORDER #${String(o.id).padStart(5, "0")}</p><h2>${esc(o.customer_name)}</h2><p>${esc(o.email)} · <span class="status ${o.status}">${o.status}</span></p>${o.note ? `<p class="order-note">${esc(o.note)}</p>` : ""}<div class="order-items">${o.items.map((i) => `<div><span>${i.quantity} × ${esc(i.name)}</span><strong>${money(i.quantity * i.unit_cents)}</strong></div>`).join("")}</div><div class="bag-total"><span>Total</span><strong>${money(o.total_cents)}</strong></div><p>${o.status === "reserved" ? `Hold expires ${date(o.expires_at)}. Verify payment externally before recording it.` : "Actions record what happened outside this app. No money is transferred."}</p><div class="admin-actions">${actions.map(([a, l]) => `<button class="outline-button" data-action="${a}" data-order-id="${o.id}">${l}</button>`).join("")}</div><div class="timeline">${o.timeline.map((e) => `<div><span>${esc(e.action)} · ${esc(e.actor)}</span><time>${date(e.created_at)}</time></div>${e.note ? `<p>${esc(e.note)}</p>` : ""}`).join("")}</div>`,
  );
}
function productForm(id) {
  const p = id
    ? desk.products.find((p) => p.id === id)
    : {
        name: "",
        description: "",
        category: "Ceramics",
        price_cents: 0,
        stock: 0,
        sku: "",
        art: "vase",
        active: 1,
      };
  formModal(
    id ? "Refine the collection." : "Something worth keeping.",
    id
      ? "Existing orders retain their original names and prices."
      : "Add a new object to your collection.",
    `<label>Name<input name="name" value="${esc(p.name)}" required maxlength="120"></label><label>Description<textarea name="description" required maxlength="1000">${esc(p.description)}</textarea></label><div class="form-grid"><label>Category<input name="category" value="${esc(p.category)}" required maxlength="50"></label><label>Price<input name="price" type="number" min="0" step="0.01" value="${(p.price_cents / 100).toFixed(2)}" required></label></div>${id ? `<label>Status<select name="active"><option value="1" ${p.active ? "selected" : ""}>Available</option><option value="0" ${p.active ? "" : "selected"}>Archived</option></select></label>` : `<div class="form-grid"><label>SKU<input name="sku" required maxlength="60"></label><label>Opening stock<input name="stock" type="number" min="0" step="1" value="0" required></label></div>`}<label>Illustration<select name="art">${["cup", "lamp", "vase", "carafe", "bowl", "tray"].map((a) => `<option ${p.art === a ? "selected" : ""}>${a}</option>`).join("")}</select></label>`,
    "Save product",
    async (f) => {
      const body = {
        name: f.get("name"),
        description: f.get("description"),
        category: f.get("category"),
        price_cents: cents(f.get("price")),
        art: f.get("art"),
      };
      if (id) body.active = Number(f.get("active"));
      else {
        body.sku = f.get("sku");
        body.stock = Number(f.get("stock"));
      }
      await api(`/api/admin/products${id ? "/" + id : ""}`, body);
      notice("Product saved.");
    },
  );
}
document.addEventListener("click", async (event) => {
  try {
    const target = event.target.closest("button");
    if (!target) return;
    if (target.dataset.category) {
      category = target.dataset.category;
      renderProducts();
    }
    if (target.dataset.add) {
      changeBag(Number(target.dataset.add), 1);
      target.textContent = "Added ✓";
      setTimeout(() => (target.textContent = "Add to bag +"), 1200);
    }
    if (target.dataset.detail) {
      const p = products.find((p) => p.id === Number(target.dataset.detail));
      modal(
        `<div class="modal-illustration">${art(p.art)}</div><p class="eyebrow">${esc(p.category)}</p><h2>${esc(p.name)}</h2><p>${esc(p.description)}</p><div class="bag-total"><span>${p.stock} available</span><strong>${money(p.price_cents)}</strong></div><button class="dark-button" data-add="${p.id}" ${p.stock ? "" : "disabled"}>Add to bag +</button>`,
      );
    }
    if (target.dataset.bagQty) {
      changeBag(Number(target.dataset.bagQty), Number(target.dataset.delta));
      showBag();
    }
    if (target.dataset.remove) {
      bag.delete(Number(target.dataset.remove));
      saveBag();
      showBag();
    }
    if (target.id === "begin-checkout") showCheckout();
    if (target.id === "refresh-order") await showOrder(orderToken);
    if (target.id === "copy-order") {
      await navigator.clipboard.writeText(
        `${location.origin}/#order=${encodeURIComponent(orderToken)}`,
      );
      target.textContent = "Link copied ✓";
    }
    if (target.id === "cancel-order") {
      target.disabled = true;
      const result = await api(
        "/api/order/cancel",
        {
          action: "cancel",
          idempotency_key: crypto.randomUUID(),
          note: "Cancelled by customer",
        },
        orderToken,
      );
      renderOrder(result);
      await loadCatalog();
    }
    if (target.dataset.tab) {
      document
        .querySelectorAll("[data-tab]")
        .forEach((b) => b.classList.toggle("active", b === target));
      $("#orders-panel").hidden = target.dataset.tab !== "orders";
      $("#inventory-panel").hidden = target.dataset.tab !== "inventory";
    }
    if (target.dataset.order) reviewOrder(Number(target.dataset.order));
    if (target.dataset.action) {
      const id = Number(target.dataset.orderId),
        action = target.dataset.action,
        key = crypto.randomUUID();
      formModal(
        {
          pay: "Record external payment.",
          ready: "Ready to collect.",
          collect: "A new home.",
          cancel: "Release this reservation.",
          refund: "Record external refund.",
        }[action],
        "This records a confirmed shop action. Payment and refunds happen outside this app.",
        `<label>${["pay", "refund"].includes(action) ? "Payment / refund reference" : "Note (optional)"}<input name="note" maxlength="400" ${["pay", "refund"].includes(action) ? "required" : ""}></label>`,
        "Confirm action",
        async (f) => {
          await api(`/api/admin/orders/${id}`, {
            action,
            idempotency_key: key,
            note: f.get("note"),
          });
          notice("Order updated.");
        },
      );
    }
    if (target.dataset.edit) productForm(Number(target.dataset.edit));
    if (target.dataset.stock) {
      const p = desk.products.find(
        (p) => p.id === Number(target.dataset.stock),
      );
      formModal(
        "Adjust available stock.",
        `${esc(p.name)} · ${p.stock} available. Active reservations are already excluded. Adjust only unreserved units.`,
        '<label>Quantity change<input name="delta" type="number" step="1" required></label><label>Reason<input name="reason" required maxlength="200"></label>',
        "Record adjustment",
        async (f) => {
          await api(`/api/admin/products/${p.id}/stock`, {
            delta: Number(f.get("delta")),
            reason: f.get("reason"),
          });
          notice("Stock adjustment recorded.");
        },
      );
    }
  } catch (error) {
    const output = $("#order-error") || $("#form-error");
    if (output) output.textContent = error.message;
    else notice(error.message, true);
  }
});
async function start() {
  try {
    const session = await api("/api/session");
    csrf = session.csrf;
    if (isAdmin) {
      if (session.admin) {
        $("#admin-login").hidden = true;
        $("#admin-workspace").hidden = false;
        $("#admin-logout").hidden = false;
        await refreshDesk();
      }
      $("#admin-login-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        const button = event.currentTarget.querySelector("button");
        button.disabled = true;
        try {
          const result = await api(
            "/api/admin/login",
            Object.fromEntries(new FormData(event.currentTarget)),
          );
          csrf = result.csrf;
          $("#admin-login").hidden = true;
          $("#admin-workspace").hidden = false;
          $("#admin-logout").hidden = false;
          await refreshDesk();
        } catch (error) {
          $("#login-error").textContent = error.message;
        } finally {
          button.disabled = false;
        }
      });
      $("#admin-logout").addEventListener("click", async () => {
        await api("/api/admin/logout", {});
        location.reload();
      });
      $("#refresh-desk").addEventListener("click", () =>
        refreshDesk().catch((e) => notice(e.message, true)),
      );
      $("#status-filter").addEventListener("change", renderDesk);
      $("#new-product").addEventListener("click", () => productForm());
    } else {
      bag = new Map(
        JSON.parse(sessionStorage.getItem("reserve-cart.bag") || "[]"),
      );
      pendingCheckout = JSON.parse(
        sessionStorage.getItem("reserve-cart.pending") || "null",
      );
      saveBag();
      await loadCatalog();
      $("#search").addEventListener("input", renderProducts);
      $("#open-bag").addEventListener("click", showBag);
      $("#track-link").addEventListener("click", () => {
        const token = sessionStorage.getItem("reserve-cart.last-order");
        if (token) showOrder(token);
        else
          modal(
            "<h2>Your private order link.</h2><p>Open the link saved after checkout. It contains your private order key. No order is stored in this browser yet.</p>",
          );
      });
      const match = location.hash.match(/^#order=([A-Za-z0-9_-]{30,100})$/);
      if (match) await showOrder(match[1]);
      else if (pendingCheckout) {
        notice(
          "A pending reservation was restored. Open your bag to retry it safely.",
        );
      }
    }
  } catch (error) {
    notice(error.message, true);
  }
}
start();
