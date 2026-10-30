// Einstellungsseite von Facade Conductor in der Seitenleiste.
// Ohne Build-Schritt: ein Web Component, Texte aus strings.json, Daten über die Websocket-Befehle in websocket.py.

const STRINGS = await fetch(new URL("./strings.json", import.meta.url))
  .then((r) => r.json())
  .catch(() => ({}));

const TABS = ["overview", "rooms", "settings"];
const SECTIONS = ["schedule", "windows", "heat", "daylight", "behavior", "about"];
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
// Eigenes Zeitfeld: type="time" zeigt je nach Sprache des Browsers AM/PM, gemeint sind aber 24 Stunden
const TIME_FIELD = 'type="text" inputmode="numeric" maxlength="5" placeholder="hh:mm" class="time" data-time';
// „7“, „730“, „7:30“ und „07:30“ werden zu „07:30“, alles andere ist ungültig
const parseTime = (text) => {
  const m = text.trim().match(/^(\d{1,2}):?(\d{2})?$/);
  if (!m || Number(m[1]) > 23 || Number(m[2] ?? 0) > 59) return undefined;
  return `${m[1].padStart(2, "0")}:${m[2] ?? "00"}`;
};
// Jedes Suchwort muss im Text vorkommen, Reihenfolge egal: „küche fenster“ findet „Fenster Küche“
const matches = (query, text) =>
  query.toLowerCase().split(/\s+/).filter(Boolean).every((word) => text.includes(word));
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
    this._open = new Set();
    this._combos = {};
    this._coverFilter = "";
    this._help = false;
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (this._menu) this._menu.hass = hass;
    if (first) this._load();
    // hass wechselt bei jeder Zustandsänderung im Haus, daher höchstens alle 2 s nachladen
    else if (!this._timer) this._timer = setTimeout(() => ((this._timer = null), this._load()), 2000);
  }

  set panel(value) {
    this._version = value?.config?.version;
  }

  set narrow(value) {
    this._narrow = value;
    if (this._menu) this._menu.narrow = value;
  }

  _t(key, vars = {}) {
    const lang = (this._hass?.locale?.language || this._hass?.language || "en").startsWith("de") ? "de" : "en";
    const text = STRINGS[lang]?.[key] ?? STRINGS.en?.[key] ?? key;
    return text.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? `{${k}}`);
  }

  // Satz mit Eingabefeldern an den Platzhaltern, etwa „Abends auf {pos} %“
  _sentence(key, parts) {
    return esc(this._t(key)).replace(/\{(\w+)\}/g, (_, k) => parts[k] ?? "");
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
    // nicht neu zeichnen, während jemand in einem Suchfeld tippt; der nächste Takt holt es nach
    if (this.shadowRoot.activeElement?.classList.contains("combo-input")) return;
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
    this._toastTimer = setTimeout(() => ((this._toast = ""), this.shadowRoot.querySelector(".toast")?.remove()), 2500);
  }

  // Zeichnen

  _render() {
    const root = this.shadowRoot;
    // ein Suchfeld nach der Auswahl nicht wieder fokussieren, sonst öffnet sich die Liste erneut
    const focused = root.activeElement?.classList.contains("combo-input") ? null : root.activeElement?.id;
    this._combos = {};
    const info = this._info;
    const body = this._error
      ? `<div class="card">${esc(this._error)}</div>`
      : !info
        ? ""
        : this[`_${this._tab}`](info);
    root.innerHTML = `
      <style>${STYLE}</style>
      <div class="toolbar">
        <ha-menu-button></ha-menu-button>
        <div class="title">Facade Conductor</div>
        ${info ? this._modes(info) : ""}
        ${info ? `<button class="help" data-help aria-expanded="${this._help}" aria-label="${esc(this._t("mode"))}">?</button>` : ""}
      </div>
      ${this._help ? this._modeHelp() : ""}
      <div class="tabs" role="tablist">
        ${TABS.map(
            (tab) =>
              `<button role="tab" data-tab="${tab}" aria-selected="${this._tab === tab}">${esc(this._t(`tab_${tab}`))}</button>`,
          )
          .join("")}
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

  _modeHelp() {
    return `<div class="helpbox">${MODES.map(
      (m) => `<p><b>${esc(this._t(`mode_${m}`))}:</b> ${esc(this._t(`mode_${m}_text`))}</p>`,
    ).join("")}</div>`;
  }

  _reasonText(room) {
    const state = this._hass.states[room.reason_entity];
    if (state && state.state === room.reason) return this._hass.formatEntityState(state);
    return this._hass.localize(`component.facade_conductor.entity.sensor.reason.state.${room.reason}`) || room.reason;
  }

  _houseInput(key, attrs) {
    const value = this._info.house[key] ?? "";
    return `<input id="h-${key}" data-house="${key}" ${attrs} value="${esc(attrs.includes("data-time") ? String(value).slice(0, 5) : value)}">`;
  }

  _housePos(key) {
    return `<input id="hp-${key}" class="pct" type="number" min="0" max="100" step="1" data-hpos="${key}"
      aria-label="${esc(this._t(`pos_${key}`))}" value="${this._info.positions[key]}">`;
  }

  // Einstellungen des Hauses: einklappbare Rubriken, der Kopf zeigt die aktuellen Werte
  _settings(info) {
    const sections = SECTIONS.map((id) => {
      const [summary, body] = this[`_sec_${id}`](info);
      return `<details class="section" data-section="${id}" ${this._open.has(id) ? "open" : ""}>
        <summary><span class="s-title">${esc(this._t(`sec_${id}`))}</span><span class="s-sum">${esc(summary)}</span></summary>
        <div class="s-body">${body}</div>
      </details>`;
    }).join("");
    return `${sections}<p class="muted">${esc(this._t("rain_wind_later"))}</p>`;
  }

  _sec_schedule(info) {
    const h = info.house;
    const p = info.positions;
    const time = (key) => this._houseInput(key, `${TIME_FIELD} aria-label="${esc(this._t(key))}"`);
    return [
      this._t("sum_schedule", {
        end: String(h.night_end).slice(0, 5), day: p.day, dusk: p.dusk, start: String(h.night_start).slice(0, 5), night: p.night,
      }),
      `<p class="sentence">${this._sentence("schedule_morning", { time: time("night_end"), pos: this._housePos("day") })}</p>
       <p class="sentence">${this._sentence("schedule_evening", { pos: this._housePos("dusk") })}</p>
       <p class="sentence">${this._sentence("schedule_night", { time: time("night_start"), pos: this._housePos("night") })}</p>
       <p class="muted">${esc(this._t("schedule_hint"))}</p>`,
    ];
  }

  _sec_windows(info) {
    const rows = info.rooms
      .filter((r) => r.data.window_sensor)
      .map(
        (r) =>
          `<div class="row"><span>${esc(r.name)} · ${esc(this._name(r.data.window_sensor))}</span>
          <span class="muted">${esc(this._stateText(r.data.window_sensor))}, ${esc(this._t("counts_as", { m: this._t(`means_${r.data.window_means || "tilted"}`) }))}</span></div>`,
      )
      .join("");
    return [
      this._t("sum_windows", { tilted: info.positions.tilted, open: info.positions.open }),
      `<p class="sentence">${this._sentence("windows_tilted", { pos: this._housePos("tilted") })}</p>
       <p class="sentence">${this._sentence("windows_open", { pos: this._housePos("open") })}</p>
       <p class="muted">${esc(this._t("windows_open_hint"))}</p>
       <h3>${esc(this._t("windows_list"))}</h3>
       ${rows || `<p class="muted">${esc(this._t("no_contact"))}</p>`}
       <p class="muted">${esc(this._t("windows_room_hint"))}</p>`,
    ];
  }

  _sec_heat(info) {
    const h = info.house;
    const weathers = Object.keys(this._hass.states).filter((id) => id.startsWith("weather."));
    return [
      h.weather
        ? this._t("sum_heat", { t: h.hot_temperature, shade: info.positions.shade, weather: this._name(h.weather) })
        : this._t("sum_heat_off"),
      `<label class="field">${esc(this._t("weather_entity"))}
         ${this._combo("h-weather", "house", "weather", weathers, h.weather)}</label>
       <div class="positions">
         <label class="field">${esc(this._t("hot_temperature"))} ${this._houseInput("hot_temperature", 'type="number" min="10" max="40" step="0.5"')}</label>
         <label class="field">${esc(this._t("pos_shade"))} ${this._housePos("shade")}</label>
       </div>
       <p class="muted">${esc(this._t("heat_hint"))}</p>`,
    ];
  }

  _sec_daylight(info) {
    const h = info.house;
    const lux = Object.keys(this._hass.states).filter(
      (id) => id.startsWith("sensor.") && this._hass.states[id].attributes.device_class === "illuminance",
    );
    const num = (key) => this._houseInput(key, 'type="number" min="0" max="100000" step="50"');
    return [
      this._t("sum_daylight", { sensor: h.lux_sensor ? this._name(h.lux_sensor) : this._t("sun_position"), dark: h.lux_dark }),
      `<label class="field">${esc(this._t("lux_sensor"))}
         ${this._combo("h-lux_sensor", "house", "lux_sensor", lux, h.lux_sensor)}</label>
       <div class="positions">
         <label class="field">${esc(this._t("lux_dark"))} ${num("lux_dark")}</label>
         <label class="field">${esc(this._t("lux_bright"))} ${num("lux_bright")}</label>
       </div>
       <p class="muted">${esc(this._t("daylight_hint"))}</p>`,
    ];
  }

  _sec_behavior(info) {
    return [
      this._t("sum_behavior", { m: info.house.rest_minutes }),
      `<label class="field">${esc(this._t("rest_minutes"))}
         ${this._houseInput("rest_minutes", 'type="number" min="0" max="240" step="1"')}</label>
       <p class="muted">${esc(this._t("behavior_hint"))}</p>`,
    ];
  }

  _sec_about() {
    const version = this._t("version", { v: this._version || "?" });
    return [
      version,
      `<p class="muted">${esc(version)} ·
         <a href="https://github.com/SekaiMedia/FaCo" target="_blank" rel="noreferrer">GitHub</a> ·
         <a href="https://sekaimedia.de" target="_blank" rel="noreferrer">SekaiMedia</a></p>`,
    ];
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
        const resume =
          r.reason === "manual" && r.manual_entity
            ? `<button class="btn" data-resume="${esc(r.manual_entity)}">${esc(this._t("resume"))}</button>`
            : "";
        return `<div class="card">
          <div class="row"><h2>${esc(r.name)}</h2><span class="big">${esc(pos)}</span></div>
          <div class="bar"><span style="width:${Number(r.position) || 0}%"></span></div>
          <div class="row">${reason}<span class="muted">${esc(this._t("target"))} ${esc(pct(r.target))}</span></div>
          <div class="row start">${resume}<button class="btn2" data-open="${esc(r.id)}">${esc(this._t("settings"))}</button></div>
        </div>`;
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

  // Suchbare Auswahl statt <select>: Tippen filtert nach Name, Entitäts-ID und Bereich
  _combo(id, kind, key, ids, selected) {
    this._combos[id] = { kind, key, ids: [...new Set([...ids, ...(selected ? [selected] : [])])] };
    return `<div class="combo" data-combo="${id}">
      <input id="${id}" class="combo-input" role="combobox" aria-autocomplete="list" aria-expanded="false"
        aria-controls="${id}-list" autocomplete="off" placeholder="${esc(this._t("search"))}"
        value="${esc(selected ? this._name(selected) : "")}" data-selected="${esc(selected || "")}">
      ${selected ? `<button class="combo-clear" aria-label="${esc(this._t("clear"))}">×</button>` : ""}
      <ul id="${id}-list" class="combo-list" role="listbox" hidden></ul>
    </div>`;
  }

  _searchText(id) {
    return `${this._name(id)} ${id} ${this._hass.areas?.[this._area(id)]?.name || ""}`.toLowerCase();
  }

  _bindCombo(combo, onPick) {
    const input = combo.querySelector("input");
    const list = combo.querySelector("ul");
    const { ids } = this._combos[combo.dataset.combo];
    const selectedName = () => (input.dataset.selected ? this._name(input.dataset.selected) : "");
    let shown = [];
    let active = -1;
    const draw = () => {
      // steht noch der gewählte Name im Feld, alles zeigen
      const query = input.value === selectedName() ? "" : input.value;
      shown = ids
        .filter((id) => matches(query, this._searchText(id)))
        .sort((a, b) => this._name(a).localeCompare(this._name(b)))
        .slice(0, 50);
      active = Math.min(active, shown.length - 1);
      list.innerHTML = shown.length
        ? shown
            .map((id, i) => {
              const area = this._hass.areas?.[this._area(id)]?.name;
              return `<li role="option" id="${combo.dataset.combo}-o${i}" data-i="${i}" aria-selected="${i === active}">
                <span>${esc(this._name(id))}</span><span class="muted">${esc(area ? `${area} · ${id}` : id)}</span></li>`;
            })
            .join("")
        : `<li class="muted">${esc(this._t("no_match"))}</li>`;
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
      if (active >= 0) input.setAttribute("aria-activedescendant", `${combo.dataset.combo}-o${active}`);
      else input.removeAttribute("aria-activedescendant");
      list.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
    };
    const close = () => {
      list.hidden = true;
      active = -1;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
    };
    const choose = (i) => {
      const id = shown[i];
      if (!id) return;
      input.dataset.selected = id;
      input.value = this._name(id);
      close();
      onPick(id);
    };
    input.addEventListener("focus", () => (input.select(), draw()));
    input.addEventListener("input", () => ((active = 0), draw()));
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        active = Math.max(0, Math.min(shown.length - 1, active + (e.key === "ArrowDown" ? 1 : -1)));
        draw();
      } else if (e.key === "Enter") {
        e.preventDefault();
        choose(Math.max(active, 0));
      } else if (e.key === "Escape") {
        input.value = selectedName();
        close();
      }
    });
    input.addEventListener("blur", () => ((input.value = selectedName()), close()));
    // mousedown statt click, sonst schließt blur die Liste vor der Auswahl
    list.addEventListener("mousedown", (e) => {
      e.preventDefault();
      const item = e.target.closest("li[data-i]");
      if (item) choose(Number(item.dataset.i));
    });
    combo.querySelector(".combo-clear")?.addEventListener("click", () => {
      input.dataset.selected = "";
      input.value = "";
      onPick(null);
    });
  }

  _filterCovers() {
    this.shadowRoot.querySelectorAll("[data-cover-label]").forEach((label) => {
      label.hidden = !label.querySelector("input").checked && !matches(this._coverFilter, label.dataset.coverLabel);
    });
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
    const sleepers = all.filter(
      (id) => /^(binary_sensor|input_boolean|switch)\./.test(id) || this._hass.states[id].attributes.device_class === "power",
    );
    const own = d.positions || {};
    const pause = d.advanced || {};
    const windowNow = d.window_sensor ? ` · ${esc(this._stateText(d.window_sensor))}` : "";
    return `
      <div class="card">
        <h2>${esc(room.name)}</h2>
        <h3>${esc(this._t("covers"))}</h3>
        <p class="muted">${esc(this._t("covers_hint"))}</p>
        <input id="f-cover-filter" class="filter" type="search" placeholder="${esc(this._t("filter_covers"))}"
          aria-label="${esc(this._t("filter_covers"))}" value="${esc(this._coverFilter)}">
        <div class="checks">
          ${covers
            .map(
              (id) =>
                `<label data-cover-label="${esc(this._searchText(id))}"><input type="checkbox" data-cover value="${esc(id)}" ${chosen.has(id) ? "checked" : ""}> ${esc(this._name(id))}</label>`,
            )
            .join("")}
        </div>
        ${chosen.size ? "" : `<div class="hint">${esc(this._t("no_covers"))}</div>`}
      </div>
      <div class="card">
        <h3>${esc(this._t("window"))}${windowNow}</h3>
        <label class="field">${esc(this._t("window_sensor"))}
          ${this._combo("f-window", "room", "window_sensor", windows, d.window_sensor)}</label>
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
          ${this._combo("f-sleep", "room", "sleep_sensor", sleepers, d.sleep_sensor)}</label>
        <p class="muted">${esc(this._t("sleep_hint"))}</p>
        ${(d.sleep_sensor || "").startsWith("sensor.")
          ? `<label class="field">${esc(this._t("sleep_watts"))}
              <input id="f-watts" type="number" min="0" max="3000" step="0.5" data-field="sleep_watts"
                value="${esc(d.sleep_watts ?? "")}" placeholder="5"></label>
             <p class="muted">${esc(this._t("sleep_watts_hint"))}</p>`
          : ""}
        <label class="field">${esc(this._t("wake_minutes"))}
          <input id="f-wake" type="number" min="0" max="120" step="1" data-field="sleep_wake_minutes"
            value="${esc(d.sleep_wake_minutes ?? "")}" placeholder="${esc(this._t("wake_now"))}"></label>
        <p class="muted">${esc(this._t("wake_hint"))}</p>
        <div class="row start">
          <label class="field">${esc(this._t("pause_start"))}
            <input id="f-pause-start" ${TIME_FIELD} data-pause="sleep_pause_start" value="${esc((pause.sleep_pause_start || "").slice(0, 5))}"></label>
          <label class="field">${esc(this._t("pause_end"))}
            <input id="f-pause-end" ${TIME_FIELD} data-pause="sleep_pause_end" value="${esc((pause.sleep_pause_end || "").slice(0, 5))}"></label>
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
    root.querySelectorAll("[data-resume]").forEach((el) =>
      el.addEventListener("click", async () => {
        await this._hass.callService("switch", "turn_off", { entity_id: el.dataset.resume });
        this._flash(this._t("saved"));
        setTimeout(() => this._load(), 2500);
      }),
    );
    root.querySelectorAll("[data-open]").forEach((el) =>
      el.addEventListener("click", () => ((this._tab = "rooms"), (this._room = el.dataset.open), this._render())),
    );
    root.querySelector("[data-help]")?.addEventListener("click", () => ((this._help = !this._help), this._render()));
    root.querySelectorAll("[data-section]").forEach((el) =>
      el.addEventListener("toggle", () => (el.open ? this._open.add(el.dataset.section) : this._open.delete(el.dataset.section))),
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

    const saveHouse = (changes) => {
      const { positions, ...rest } = changes;
      Object.assign(this._info.house, rest);
      if (positions) Object.assign(this._info.positions, positions);
      return this._call({ type: "facade_conductor/house/update", changes });
    };
    root.querySelectorAll("[data-house]").forEach((el) =>
      el.addEventListener("change", () => {
        if (el.tagName === "SELECT") return saveHouse({ [el.dataset.house]: el.value || null });
        if (el.value === "") return; // Pflichtfeld: leer heißt nichts ändern
        if (el.dataset.time === undefined) return saveHouse({ [el.dataset.house]: Number(el.value) });
        const time = parseTime(el.value);
        if (!time) return this._flash(this._t("time_invalid"));
        saveHouse({ [el.dataset.house]: `${time}:00` });
      }),
    );
    root.querySelectorAll("[data-hpos]").forEach((el) =>
      el.addEventListener("change", () => el.value !== "" && saveHouse({ positions: { [el.dataset.hpos]: Number(el.value) } })),
    );

    const save = (changes) => {
      // sofort übernehmen, sonst springt das Feld bis zum Nachladen auf den alten Wert
      const room = this._info.rooms.find((r) => r.id === this._room);
      room.data = { ...room.data, ...changes };
      return this._call({ type: "facade_conductor/room/update", room_id: this._room, changes });
    };
    root.querySelectorAll(".combo").forEach((combo) =>
      this._bindCombo(combo, (value) => {
        const { kind, key } = this._combos[combo.dataset.combo];
        (kind === "house" ? saveHouse : save)({ [key]: value });
      }),
    );
    root.getElementById("f-cover-filter")?.addEventListener("input", (e) => {
      this._coverFilter = e.target.value;
      this._filterCovers();
    });
    this._filterCovers();
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
        root.querySelectorAll("[data-pause]").forEach((p) => (advanced[p.dataset.pause] = p.value ? parseTime(p.value) : null));
        if (Object.values(advanced).includes(undefined)) return this._flash(this._t("time_invalid"));
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
  .content { padding: 16px; max-width: 1200px; display: flex; flex-direction: column; gap: 16px; }
  .card { background: var(--card-background-color); border-radius: var(--ha-card-border-radius, 12px); border: 1px solid var(--divider-color); padding: 16px; display: flex; flex-direction: column; gap: 12px; color: inherit; font: inherit; text-align: left; }
  h2 { margin: 0; font-size: 18px; font-weight: 500; } h3 { margin: 0; font-size: 16px; font-weight: 500; }
  .sentence { margin: 0; font-size: 16px; line-height: 2.4; }
  .sentence input { margin: 0 4px; }
  input.pct { width: 72px; }
  input.time { width: 72px; }
  .section { background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: var(--ha-card-border-radius, 12px); }
  .section summary { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 16px; padding: 14px 16px; min-height: 24px; cursor: pointer; list-style: none; }
  .section summary::-webkit-details-marker { display: none; }
  .section summary::before { content: "▸"; color: var(--secondary-text-color); transition: transform .15s; }
  .section[open] summary::before { transform: rotate(90deg); }
  .s-title { font-size: 16px; font-weight: 500; }
  .s-sum { font-size: 14px; color: var(--secondary-text-color); }
  .s-body { display: flex; flex-direction: column; gap: 12px; padding: 0 16px 16px; }
  .help { font: inherit; font-weight: 700; width: 32px; height: 32px; border-radius: 50%; border: 1px solid currentColor; background: none; color: inherit; cursor: pointer; }
  .helpbox { background: var(--card-background-color); border-bottom: 1px solid var(--divider-color); padding: 4px 16px; font-size: 14px; }
  .helpbox p { margin: 8px 0; }
  .combo { position: relative; }
  input.combo-input { width: 100%; box-sizing: border-box; padding-right: 36px; }
  .combo-clear { position: absolute; right: 4px; top: 4px; width: 32px; height: 32px; border: 0; border-radius: 50%; background: none; color: var(--secondary-text-color); font-size: 20px; cursor: pointer; }
  .combo-list { position: absolute; z-index: 5; left: 0; right: 0; top: 100%; margin: 2px 0 0; padding: 4px 0; list-style: none; max-height: 280px; overflow: auto; background: var(--card-background-color); border: 1px solid var(--divider-color); border-radius: 6px; box-shadow: 0 4px 12px rgba(0, 0, 0, .3); }
  .combo-list li { display: flex; flex-direction: column; gap: 2px; padding: 6px 12px; font-size: 14px; color: var(--primary-text-color); cursor: pointer; }
  .combo-list li[aria-selected="true"], .combo-list li[data-i]:hover { background: rgba(var(--rgb-primary-color, 3, 169, 244), .15); }
  .combo-list li .muted { font-size: 12px; }
  input.filter { max-width: 320px; }
  .muted { color: var(--secondary-text-color); font-size: 14px; margin: 0; }
  .hint { background: rgba(255, 166, 0, .15); border-radius: 8px; padding: 10px 14px; font-size: 14px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
  .btn2 { font: inherit; font-size: 14px; font-weight: 500; min-height: 36px; padding: 0 14px; border-radius: 18px; border: 1px solid var(--divider-color); background: none; color: var(--primary-text-color); cursor: pointer; }
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
  select, input[type=number], input.time, input.combo-input, input.filter { font: inherit; font-size: 15px; min-height: 40px; padding: 0 10px; border-radius: 6px; border: 1px solid var(--divider-color); background: var(--secondary-background-color, transparent); color: var(--primary-text-color); }
  .checks { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 4px 16px; max-height: 260px; overflow: auto; }
  .checks label { display: flex; align-items: center; gap: 8px; min-height: 32px; font-size: 14px; }
  .positions { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; }
  .btn { font: inherit; font-size: 14px; font-weight: 500; min-height: 40px; padding: 0 16px; border-radius: 20px; border: 0; background: var(--primary-color); color: var(--text-primary-color, #fff); cursor: pointer; }
  .btn.danger { background: none; border: 1px solid var(--error-color, #db4437); color: var(--error-color, #db4437); }
  .toast { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); background: #323232; color: #fff; padding: 12px 20px; border-radius: 8px; font-size: 14px; }
`;

if (!customElements.get("facade-conductor-panel")) customElements.define("facade-conductor-panel", FacadeConductorPanel);
