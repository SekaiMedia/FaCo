// Einstellungsseite von Facade Conductor in der Seitenleiste.
// Ohne Build-Schritt: ein Web Component, Texte aus strings.json, Daten über die Websocket-Befehle in websocket.py.

const STRINGS = await fetch(new URL("./strings.json", import.meta.url))
  .then((r) => r.json())
  .catch(() => ({}));

const MODES = ["off", "dry_run", "auto"];
const DIRECTIONS = ["none", "n", "ne", "e", "se", "s", "sw", "w", "nw"];
const POSITIONS = ["day", "dusk", "night", "tilted", "open", "shade"];
const WINDOW_CLASSES = ["window", "door", "opening", "garage_door"];
const REASON_COLOR = {
  schedule: "var(--info-color, #039be5)",
  evening_cooling: "var(--info-color, #039be5)",
  heat_protection: "var(--warning-color, #ffa600)",
  window_tilted: "var(--success-color, #43a047)",
  window_open: "var(--success-color, #43a047)",
  sleep: "var(--secondary-text-color)",
  manual: "var(--primary-text-color)",
  safety: "var(--error-color, #db4437)",
};

const pct = (v) => (v == null ? "–" : `${v} %`);
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

class FacadeConductorPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "overview";
    this._room = null;
    this._info = null;
    this._key = null;
    this._toast = "";
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (this._menu) this._menu.hass = hass;
    if (first) this._load();
    // hass wechselt bei jeder Zustandsänderung im Haus, daher höchstens alle 2 s nachladen
    else if (!this._timer) this._timer = setTimeout(() => ((this._timer = null), this._load()), 2000);
  }

  set narrow(value) {
    this._narrow = value;
    if (this._menu) this._menu.narrow = value;
  }

  _t(key, vars = {}) {
    const lang = (this._hass?.locale?.language || this._hass?.language || "en").startsWith("de") ? "de" : "en";
    const text = STRINGS[lang]?.[key] ?? STRINGS.en?.[key] ?? key;
    return text.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "");
  }

  _name(entityId) {
    return this._hass.states[entityId]?.attributes.friendly_name || entityId;
  }

  _stateText(entityId) {
    const state = this._hass.states[entityId];
    return state ? this._hass.formatEntityState(state) : "";
  }

  _area(entityId) {
    const entity = this._hass.entities?.[entityId];
    return entity?.area_id || this._hass.devices?.[entity?.device_id]?.area_id || null;
  }

  async _load() {
    let info = null;
    let error = null;
    try {
      info = await this._hass.callWS({ type: "facade_conductor/info" });
    } catch (err) {
      error = err.message || err.code || String(err);
    }
    // nur neu zeichnen, wenn sich etwas Sichtbares geändert hat, sonst springt der Cursor
    const windows = (info?.rooms || []).map((r) => this._stateText(r.data.window_sensor)).join("|");
    const key = JSON.stringify([info, error, windows]);
    if (key === this._key) return;
    this._key = key;
    this._info = info;
    this._error = error;
    this._render();
  }

  _reloadSoon() {
    // Speichern lädt die Integration neu, das dauert einen Moment
    setTimeout(() => this._load(), 1500);
  }

  async _call(message, toast = this._t("saved")) {
    try {
      const result = await this._hass.callWS(message);
      this._flash(toast);
      this._reloadSoon();
      return result;
    } catch (err) {
      this._flash(this._t("error", { msg: err.message || err.code }));
      return null;
    }
  }

  _flash(text) {
    this._toast = text;
    this._render();
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => ((this._toast = ""), this._render()), 2500);
  }

  // Zeichnen

  _render() {
    const root = this.shadowRoot;
    const focused = root.activeElement?.id;
    const info = this._info;
    const body = this._error
      ? `<div class="card">${esc(this._error)}</div>`
      : !info
        ? ""
        : this._tab === "overview"
          ? this._overview(info)
          : this._rooms(info);
    root.innerHTML = `
      <style>${STYLE}</style>
      <div class="toolbar">
        <ha-menu-button></ha-menu-button>
        <div class="title">Facade Conductor</div>
        ${info ? this._modes(info) : ""}
      </div>
      <div class="tabs" role="tablist">
        ${["overview", "rooms"]
          .map(
            (tab) =>
              `<button role="tab" data-tab="${tab}" aria-selected="${this._tab === tab}">${esc(this._t(`tab_${tab}`))}</button>`,
          )
          .join("")}
        <a class="more" href="/config/integrations/integration/facade_conductor">${esc(this._t("house_settings"))}</a>
      </div>
      <div class="content">${body}</div>
      ${this._toast ? `<div class="toast" role="status">${esc(this._toast)}</div>` : ""}`;
    this._menu = root.querySelector("ha-menu-button");
    this._menu.hass = this._hass;
    this._menu.narrow = this._narrow;
    if (focused) root.getElementById(focused)?.focus();
    this._bind();
  }

  _modes(info) {
    return `<div class="seg" role="radiogroup" aria-label="${esc(this._t("mode"))}">
      ${MODES.map(
        (m) =>
          `<button role="radio" data-mode="${m}" aria-checked="${info.mode === m}"><span class="dot ${m}"></span>${esc(this._t(`mode_${m}`))}</button>`,
      ).join("")}
    </div>`;
  }

  _reasonText(room) {
    const state = this._hass.states[room.reason_entity];
    if (state && state.state === room.reason) return this._hass.formatEntityState(state);
    return this._hass.localize(`component.facade_conductor.entity.sensor.reason.state.${room.reason}`) || room.reason;
  }

  _overview(info) {
    const hint =
      info.mode === "auto" ? "" : `<div class="hint">${esc(this._t(info.mode === "off" ? "hint_off" : "hint_dry_run"))}</div>`;
    const phase = info.phase ? `<p class="muted">${esc(this._t("phase"))}: ${esc(this._t(`phase_${info.phase}`))}</p>` : "";
    if (!info.rooms.length) return `${hint}<div class="card"><p>${esc(this._t("no_rooms"))}</p></div>`;
    const cards = info.rooms
      .map((r) => {
        const pos = pct(r.position);
        const reason = r.reason
          ? `<span class="chip" style="--c:${REASON_COLOR[r.reason] || "var(--secondary-text-color)"}">${esc(this._reasonText(r))}</span>`
          : `<span class="muted">${esc(this._t("waiting"))}</span>`;
        const window = r.data.window_sensor ? this._stateText(r.data.window_sensor) : this._t("no_contact");
        return `<button class="card room-card" data-open="${esc(r.id)}">
          <div class="row"><h2>${esc(r.name)}</h2><span class="big">${esc(pos)}</span></div>
          <div class="bar"><span style="width:${Number(r.position) || 0}%"></span></div>
          <div class="row">${reason}<span class="muted">${esc(this._t("target"))} ${esc(pct(r.target))}</span></div>
          <div class="muted">${esc(this._t("window"))}: ${esc(window)}</div>
        </button>`;
      })
      .join("");
    return `${hint}${phase}<div class="grid">${cards}</div>`;
  }

  _rooms(info) {
    const used = new Set(info.rooms.map((r) => r.data.area));
    const free = Object.values(this._hass.areas || {})
      .filter((a) => !used.has(a.area_id))
      .sort((a, b) => a.name.localeCompare(b.name));
    if (!info.rooms.some((r) => r.id === this._room)) this._room = info.rooms[0]?.id ?? null;
    const list = info.rooms
      .map(
        (r) =>
          `<button class="room" data-room="${esc(r.id)}" aria-selected="${r.id === this._room}"><span>${esc(r.name)}</span><span class="muted">${esc(pct(r.position))}</span></button>`,
      )
      .join("");
    const add = free.length
      ? `<div class="add">
          <select id="add-area" aria-label="${esc(this._t("choose_area"))}">
            <option value="">${esc(this._t("choose_area"))}</option>
            ${free.map((a) => `<option value="${esc(a.area_id)}">${esc(a.name)}</option>`).join("")}
          </select>
          <button class="btn" data-action="add">${esc(this._t("add_room"))}</button>
        </div>`
      : `<p class="muted">${esc(this._t("all_areas_used"))}</p>`;
    const room = info.rooms.find((r) => r.id === this._room);
    return `<div class="split">
      <div class="card list">${list}${add}</div>
      <div class="detail">${room ? this._roomForm(room, info) : ""}</div>
    </div>`;
  }

  _options(entityIds, selected, emptyLabel) {
    const ids = [...new Set([...entityIds, ...(selected ? [selected] : [])])].sort((a, b) =>
      this._name(a).localeCompare(this._name(b)),
    );
    return `<option value="">${esc(emptyLabel)}</option>${ids
      .map((id) => `<option value="${esc(id)}" ${id === selected ? "selected" : ""}>${esc(this._name(id))}</option>`)
      .join("")}`;
  }

  _roomForm(room, info) {
    const d = room.data;
    const all = Object.keys(this._hass.states);
    const covers = all
      .filter((id) => id.startsWith("cover."))
      .sort(
        (a, b) =>
          (this._area(b) === d.area) - (this._area(a) === d.area) || this._name(a).localeCompare(this._name(b)),
      );
    const chosen = new Set(d.covers || []);
    const windows = all.filter(
      (id) => id.startsWith("binary_sensor.") && WINDOW_CLASSES.includes(this._hass.states[id].attributes.device_class),
    );
    const sleepers = all.filter((id) => id.startsWith("binary_sensor.") || id.startsWith("input_boolean."));
    const own = d.positions || {};
    const pause = d.advanced || {};
    const windowNow = d.window_sensor ? ` · ${esc(this._stateText(d.window_sensor))}` : "";
    return `
      <div class="card">
        <h2>${esc(room.name)}</h2>
        <h3>${esc(this._t("covers"))}</h3>
        <p class="muted">${esc(this._t("covers_hint"))}</p>
        <div class="checks">
          ${covers
            .map(
              (id) =>
                `<label><input type="checkbox" data-cover value="${esc(id)}" ${chosen.has(id) ? "checked" : ""}> ${esc(this._name(id))}</label>`,
            )
            .join("")}
        </div>
        ${chosen.size ? "" : `<div class="hint">${esc(this._t("no_covers"))}</div>`}
      </div>
      <div class="card">
        <h3>${esc(this._t("window"))}${windowNow}</h3>
        <label class="field">${esc(this._t("window_sensor"))}
          <select id="f-window" data-field="window_sensor">${this._options(windows, d.window_sensor, this._t("none"))}</select></label>
        <label class="field">${esc(this._t("window_means"))}
          <select id="f-means" data-field="window_means">
            ${["tilted", "open"].map((m) => `<option value="${m}" ${(d.window_means || "tilted") === m ? "selected" : ""}>${esc(this._t(`means_${m}`))}</option>`).join("")}
          </select></label>
        <p class="muted">${esc(this._t("window_means_hint"))}</p>
      </div>
      <div class="card">
        <h3>${esc(this._t("sun"))}</h3>
        <label class="field">${esc(this._t("direction"))}
          <select id="f-direction" data-field="direction">
            ${DIRECTIONS.map((x) => `<option value="${x}" ${(d.direction || "none") === x ? "selected" : ""}>${esc(this._t(`dir_${x}`))}</option>`).join("")}
          </select></label>
        <p class="muted">${esc(this._t("direction_hint"))}</p>
      </div>
      <div class="card">
        <h3>${esc(this._t("sleep"))}</h3>
        <label class="field">${esc(this._t("sleep_sensor"))}
          <select id="f-sleep" data-field="sleep_sensor">${this._options(sleepers, d.sleep_sensor, this._t("none"))}</select></label>
        <p class="muted">${esc(this._t("sleep_hint"))}</p>
        <div class="row start">
          <label class="field">${esc(this._t("pause_start"))}
            <input id="f-pause-start" type="time" data-pause="sleep_pause_start" value="${esc((pause.sleep_pause_start || "").slice(0, 5))}"></label>
          <label class="field">${esc(this._t("pause_end"))}
            <input id="f-pause-end" type="time" data-pause="sleep_pause_end" value="${esc((pause.sleep_pause_end || "").slice(0, 5))}"></label>
        </div>
        <p class="muted">${esc(this._t("pause_hint"))}</p>
      </div>
      <div class="card">
        <h3>${esc(this._t("positions"))}</h3>
        <p class="muted">${esc(this._t("positions_hint"))}</p>
        <div class="positions">
          ${POSITIONS.map(
            (k) => `<label class="field">${esc(this._t(`pos_${k}`))}
              <input id="f-pos-${k}" type="number" min="0" max="100" step="1" data-pos="${k}"
                value="${own[k] ?? ""}" placeholder="${esc(this._t("like_house", { v: info.positions[k] }))}"></label>`,
          ).join("")}
        </div>
      </div>
      <div><button class="btn danger" data-action="remove">${esc(this._t("remove_room"))}</button></div>`;
  }

  // Bedienen

  _bind() {
    const root = this.shadowRoot;
    root.querySelectorAll("[data-tab]").forEach((el) =>
      el.addEventListener("click", () => ((this._tab = el.dataset.tab), this._render())),
    );
    root.querySelectorAll("[data-open]").forEach((el) =>
      el.addEventListener("click", () => ((this._tab = "rooms"), (this._room = el.dataset.open), this._render())),
    );
    root.querySelectorAll("[data-room]").forEach((el) =>
      el.addEventListener("click", () => ((this._room = el.dataset.room), this._render())),
    );
    root.querySelectorAll("[data-mode]").forEach((el) =>
      el.addEventListener("click", async () => {
        await this._hass.callService("select", "select_option", {
          entity_id: this._info.mode_entity,
          option: el.dataset.mode,
        });
        setTimeout(() => this._load(), 300);
      }),
    );
    root.querySelector("[data-action=add]")?.addEventListener("click", async () => {
      const area = root.getElementById("add-area").value;
      if (!area) return;
      const result = await this._call({ type: "facade_conductor/room/add", area });
      if (result) this._room = result.id;
    });
    root.querySelector("[data-action=remove]")?.addEventListener("click", () => {
      const room = this._info.rooms.find((r) => r.id === this._room);
      if (room && confirm(this._t("confirm_remove", { name: room.name })))
        this._call({ type: "facade_conductor/room/remove", room_id: room.id });
    });

    const save = (changes) => {
      // sofort übernehmen, sonst springt das Feld bis zum Nachladen auf den alten Wert
      const room = this._info.rooms.find((r) => r.id === this._room);
      room.data = { ...room.data, ...changes };
      return this._call({ type: "facade_conductor/room/update", room_id: this._room, changes });
    };
    root.querySelectorAll("[data-cover]").forEach((el) =>
      el.addEventListener("change", () =>
        save({ covers: [...root.querySelectorAll("[data-cover]:checked")].map((c) => c.value) }),
      ),
    );
    root.querySelectorAll("[data-field]").forEach((el) =>
      el.addEventListener("change", () => save({ [el.dataset.field]: el.value || null })),
    );
    root.querySelectorAll("[data-pause]").forEach((el) =>
      el.addEventListener("change", () => {
        const advanced = {};
        root.querySelectorAll("[data-pause]").forEach((p) => (advanced[p.dataset.pause] = p.value || null));
        save({ advanced });
      }),
    );
    root.querySelectorAll("[data-pos]").forEach((el) =>
      el.addEventListener("change", () => {
        const positions = {};
        root.querySelectorAll("[data-pos]").forEach((p) => (positions[p.dataset.pos] = p.value === "" ? null : Number(p.value)));
        save({ positions });
      }),
    );
  }
}

const STYLE = `
  :host { display: block; min-height: 100vh; background: var(--primary-background-color); color: var(--primary-text-color); font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); }
  .toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; min-height: 56px; padding: 4px 16px; background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, #fff); }
  .title { flex: 1; font-size: 20px; }
  .seg { display: inline-flex; border: 1px solid currentColor; border-radius: 18px; overflow: hidden; }
  .seg button { font: inherit; font-size: 14px; display: inline-flex; align-items: center; gap: 8px; min-height: 36px; padding: 0 14px; background: none; border: 0; border-left: 1px solid currentColor; color: inherit; cursor: pointer; opacity: .75; }
  .seg button:first-child { border-left: 0; }
  .seg button[aria-checked="true"] { background: rgba(255,255,255,.2); opacity: 1; font-weight: 500; }
  .dot { width: 8px; height: 8px; border-radius: 50%; }
  .dot.off { background: #9e9e9e; } .dot.dry_run { background: #ffb74d; } .dot.auto { background: #81c784; }
  .tabs { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; padding: 0 16px; border-bottom: 1px solid var(--divider-color); background: var(--card-background-color); }
  .tabs button { font: inherit; font-size: 14px; font-weight: 500; min-height: 48px; padding: 0 16px; background: none; border: 0; border-bottom: 3px solid transparent; color: var(--secondary-text-color); cursor: pointer; }
  .tabs button[aria-selected="true"] { color: var(--primary-color); border-bottom-color: var(--primary-color); }
  .more { margin-left: auto; font-size: 14px; color: var(--primary-color); padding: 12px 0; }
  .content { padding: 16px; max-width: 1200px; margin: 0 auto; display: flex; flex-direction: column; gap: 16px; }
  .card { background: var(--card-background-color); border-radius: var(--ha-card-border-radius, 12px); border: 1px solid var(--divider-color); padding: 16px; display: flex; flex-direction: column; gap: 12px; color: inherit; font: inherit; text-align: left; }
  h2 { margin: 0; font-size: 18px; font-weight: 500; } h3 { margin: 0; font-size: 16px; font-weight: 500; }
  .muted { color: var(--secondary-text-color); font-size: 14px; margin: 0; }
  .hint { background: rgba(255, 166, 0, .15); border-radius: 8px; padding: 10px 14px; font-size: 14px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
  .room-card { cursor: pointer; }
  .row { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
  .row.start { justify-content: flex-start; }
  .big { font-size: 24px; }
  .bar { height: 6px; border-radius: 3px; background: var(--divider-color); overflow: hidden; }
  .bar span { display: block; height: 100%; background: var(--primary-color); }
  .chip { font-size: 13px; font-weight: 500; padding: 4px 10px; border-radius: 14px; color: var(--c); border: 1px solid var(--c); }
  .split { display: grid; grid-template-columns: minmax(200px, 260px) minmax(0, 1fr); gap: 16px; align-items: start; }
  @media (max-width: 760px) { .split { grid-template-columns: 1fr; } }
  .list { gap: 4px; padding: 8px; }
  .room { font: inherit; display: flex; justify-content: space-between; gap: 8px; min-height: 44px; padding: 8px 12px; border: 0; border-radius: 8px; background: none; color: inherit; cursor: pointer; text-align: left; }
  .room[aria-selected="true"] { background: rgba(var(--rgb-primary-color, 3, 169, 244), .2); }
  .add { display: flex; flex-direction: column; gap: 8px; border-top: 1px solid var(--divider-color); padding-top: 12px; margin-top: 8px; }
  .detail { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
  .field { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--secondary-text-color); }
  select, input[type=number], input[type=time] { font: inherit; font-size: 15px; min-height: 40px; padding: 0 10px; border-radius: 6px; border: 1px solid var(--divider-color); background: var(--secondary-background-color, transparent); color: var(--primary-text-color); }
  .checks { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 4px 16px; max-height: 260px; overflow: auto; }
  .checks label { display: flex; align-items: center; gap: 8px; min-height: 32px; font-size: 14px; }
  .positions { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; }
  .btn { font: inherit; font-size: 14px; font-weight: 500; min-height: 40px; padding: 0 16px; border-radius: 20px; border: 0; background: var(--primary-color); color: var(--text-primary-color, #fff); cursor: pointer; }
  .btn.danger { background: none; border: 1px solid var(--error-color, #db4437); color: var(--error-color, #db4437); }
  .toast { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); background: #323232; color: #fff; padding: 12px 20px; border-radius: 8px; font-size: 14px; }
`;

if (!customElements.get("facade-conductor-panel")) customElements.define("facade-conductor-panel", FacadeConductorPanel);
