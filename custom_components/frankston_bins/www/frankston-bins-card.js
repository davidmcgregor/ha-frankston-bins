/*
 * Frankston Bins card
 *
 * Shows which bins go out at the next collection, as coloured wheelie bins,
 * plus the next few collection days. Point it at the integration's
 * "Next collection" sensor:
 *
 *   type: custom:frankston-bins-card
 *   entity: sensor.frankston_bins_next_collection
 */

const BIN_SVG = (lid, active) => `
<svg viewBox="0 0 64 64" aria-hidden="true">
  <g opacity="${active ? 1 : 0.35}">
    <path d="M14 18h36l-4 38a3 3 0 0 1-3 2.7H21a3 3 0 0 1-3-2.7z" fill="${active ? "#3d4a3f" : "#8a8f93"}"/>
    <path d="M20 24h3l2 28h-3zM30.5 24h3v28h-3zM41 24h3l-2 28h-3z" fill="#000" opacity=".18"/>
    <rect x="9" y="10" width="46" height="9" rx="2.5" fill="${active ? lid : "#b5b9bc"}"/>
    <rect x="25" y="6" width="14" height="5" rx="2" fill="${active ? lid : "#b5b9bc"}"/>
    <circle cx="20" cy="58" r="4.5" fill="#222"/><circle cx="20" cy="58" r="1.8" fill="#777"/>
    <circle cx="44" cy="58" r="4.5" fill="#222"/><circle cx="44" cy="58" r="1.8" fill="#777"/>
  </g>
</svg>`;

const SHORT_NAMES = {
  general_waste: "General",
  recycling: "Recycling",
  fogo: "FOGO",
  glass: "Glass",
};

const parseDate = (iso) => {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
};

const escapeHtml = (text) =>
  String(text).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

class FrankstonBinsCard extends HTMLElement {
  static getConfigForm() {
    return {
      schema: [
        {
          name: "entity",
          required: true,
          selector: { entity: { integration: "frankston_bins", domain: "sensor" } },
        },
        { name: "title", selector: { text: {} } },
        {
          name: "upcoming",
          selector: { number: { min: 0, max: 8, mode: "box" } },
        },
        { name: "show_names", selector: { boolean: {} } },
      ],
      computeLabel: (schema) =>
        ({
          entity: "Next collection sensor",
          title: "Title",
          upcoming: "Upcoming collections to list",
          show_names: "Show bin names",
        })[schema.name],
    };
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (id) => id.startsWith("sensor.") && hass.states[id].attributes.bin_details
    );
    return { entity: entity || "", upcoming: 3 };
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("Set 'entity' to the Frankston Bins 'Next collection' sensor");
    }
    this._config = { upcoming: 3, show_names: true, ...config };
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._lastState = undefined;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const state = hass.states[this._config.entity];
    if (state !== this._lastState) {
      this._lastState = state;
      this._render();
    }
  }

  getCardSize() {
    return 3 + Math.ceil((this._config?.upcoming || 0) / 2);
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  _locale() {
    return this._hass?.locale?.language || this._hass?.language || navigator.language;
  }

  _format(date, options) {
    return new Intl.DateTimeFormat(this._locale(), options).format(date);
  }

  _when(iso, daysUntil) {
    if (daysUntil === 0) return "Today";
    if (daysUntil === 1) return "Tomorrow";
    if (daysUntil > 1 && daysUntil < 7) return this._format(parseDate(iso), { weekday: "long" });
    return this._format(parseDate(iso), { weekday: "short", day: "numeric", month: "short" });
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const state = this._lastState;
    const title = this._config.title ?? "Bins";

    if (!state || !state.attributes.bin_details) {
      this.shadowRoot.innerHTML = `
        <ha-card header="${escapeHtml(title)}">
          <div class="card-content">Entity ${escapeHtml(this._config.entity)} not found.
          Pick the Frankston Bins "Next collection" sensor.</div>
        </ha-card>`;
      return;
    }

    const attrs = state.attributes;
    const details = attrs.bin_details;
    const colours = Object.fromEntries(details.map((d) => [d.key, d.colour]));
    const names = Object.fromEntries(details.map((d) => [d.key, d.name]));
    const daysUntil = attrs.days_until;
    const binNight = daysUntil <= 1;
    const dateLabel = this._format(parseDate(state.state), {
      weekday: "long",
      day: "numeric",
      month: "long",
    });

    const subtitle =
      daysUntil <= 1
        ? `${this._when(state.state, daysUntil)} · ${dateLabel}`
        : `${dateLabel} · in ${daysUntil} days`;

    const bins = details
      .map((bin) => {
        const sub = bin.going_out
          ? `<span class="badge" style="--bin:${bin.colour}">Out</span>`
          : `<span class="next">${escapeHtml(this._when(bin.next_date, bin.days_until))}</span>`;
        return `
          <div class="bin ${bin.going_out ? "on" : "off"}" title="${escapeHtml(bin.name)} (${escapeHtml(bin.lid)} lid)">
            ${BIN_SVG(bin.colour, bin.going_out)}
            ${this._config.show_names ? `<div class="name">${escapeHtml(SHORT_NAMES[bin.key] || bin.name)}</div>` : ""}
            ${sub}
          </div>`;
      })
      .join("");

    const upcoming = (attrs.upcoming || [])
      .slice(1, 1 + Number(this._config.upcoming || 0))
      .map((c) => {
        const days = Math.round((parseDate(c.date) - parseDate(state.state)) / 86400000) + daysUntil;
        const dots = c.bins
          .map((k) => `<span class="dot" style="background:${colours[k]}" title="${escapeHtml(names[k])}"></span>`)
          .join("");
        const label = c.bins.map((k) => SHORT_NAMES[k] || names[k]).join(", ");
        return `
          <div class="row">
            <span class="when">${escapeHtml(this._when(c.date, days))}</span>
            <span class="dots">${dots}</span>
            <span class="label">${escapeHtml(label)}</span>
          </div>`;
      })
      .join("");

    this.shadowRoot.innerHTML = `
      <style>
        ha-card { overflow: hidden; }
        .header { display: flex; align-items: center; gap: 12px; padding: 16px 16px 4px; cursor: pointer; }
        .header ha-icon { --mdc-icon-size: 28px; color: var(--state-icon-color); }
        .header.alert ha-icon { color: var(--warning-color, #ffa600); }
        .title { font-size: 1.15em; font-weight: 500; color: var(--primary-text-color); }
        .subtitle { color: var(--secondary-text-color); font-size: 0.95em; }
        .alert .subtitle { color: var(--primary-text-color); }
        .bins { display: flex; justify-content: space-around; gap: 8px; padding: 12px 12px 8px; }
        .bin { flex: 1 1 0; display: flex; flex-direction: column; align-items: center; gap: 4px; min-width: 0; cursor: pointer; }
        .bin svg { width: 100%; max-width: 64px; height: auto; transition: transform .2s; }
        .bin.on svg { filter: drop-shadow(0 2px 3px rgba(0,0,0,.3)); }
        .bin.off .name { color: var(--secondary-text-color); }
        .name { font-size: .85em; font-weight: 500; color: var(--primary-text-color); text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
        .badge { font-size: .75em; font-weight: 600; padding: 1px 8px; border-radius: 10px; color: #fff; background: var(--bin); text-shadow: 0 0 2px rgba(0,0,0,.5); }
        .next { font-size: .75em; color: var(--secondary-text-color); white-space: nowrap; }
        .upcoming { border-top: 1px solid var(--divider-color); padding: 8px 16px 12px; }
        .row { display: grid; grid-template-columns: 7.5em 3.5em 1fr; gap: 10px; align-items: center; padding: 3px 0; font-size: .9em; }
        .when { color: var(--primary-text-color); }
        .dots { display: flex; gap: 4px; }
        .dot { width: 12px; height: 12px; border-radius: 50%; border: 1px solid rgba(0,0,0,.25); }
        .label { color: var(--secondary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      </style>
      <ha-card>
        <div class="header ${binNight ? "alert" : ""}">
          <ha-icon icon="${binNight ? "mdi:delete-alert" : "mdi:delete-variant"}"></ha-icon>
          <div>
            <div class="title">${escapeHtml(title)}${binNight ? (daysUntil === 0 ? ": collection today" : ": put them out tonight") : ""}</div>
            <div class="subtitle">${escapeHtml(subtitle)}</div>
          </div>
        </div>
        <div class="bins">${bins}</div>
        ${upcoming ? `<div class="upcoming">${upcoming}</div>` : ""}
      </ha-card>`;

    this.shadowRoot.querySelectorAll(".header, .bin").forEach((el) =>
      el.addEventListener("click", () => this._moreInfo())
    );
  }

  _moreInfo() {
    this.dispatchEvent(
      new CustomEvent("hass-more-info", {
        detail: { entityId: this._config.entity },
        bubbles: true,
        composed: true,
      })
    );
  }
}

// Home Assistant loads this script before its own frontend. On some browsers
// (older Safari/iOS, which get the compatibility build, or Safari's custom
// element registry polyfill) the frontend then swaps in a different
// window.customElements, and anything defined earlier is invisible to it: the
// card picker spins forever. So wait until the frontend has defined
// <home-assistant> on the registry it actually uses, and register there.
const register = () => {
  const registry = window.customElements;
  if (!registry.get("frankston-bins-card")) {
    registry.define("frankston-bins-card", FrankstonBinsCard);
  }
  window.customCards = window.customCards || [];
  if (!window.customCards.some((card) => card.type === "frankston-bins-card")) {
    window.customCards.push({
      type: "frankston-bins-card",
      name: "Frankston Bins",
      description: "Which bins go out at the next Frankston City Council collection.",
      preview: true,
      documentationURL: "https://github.com/davidmcgregor/ha-frankston-bins",
    });
  }
};

const waitForFrontend = (deadline) => {
  if (window.customElements.get("home-assistant") || Date.now() > deadline) {
    register();
  } else {
    setTimeout(() => waitForFrontend(deadline), 50);
  }
};

waitForFrontend(Date.now() + 30000);
