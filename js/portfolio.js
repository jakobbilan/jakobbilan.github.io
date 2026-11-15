/* Portfolio page: loads the coding-challenge charts the way project/js/project.js loads the project's charts
   (same theme, number formats, tooltips and loading states), and wires the page's small extras */

(function () {
    "use strict";

    const THEME = "project/charts/theme.json";
    const narrow = window.matchMedia("(max-width: 40rem)");

    // Same locale as the project: £ for currency formats ("$,.0f"), British month names
    const numberLocale = { decimal: ".", thousands: ",", grouping: [3], currency: ["£", ""] };
    const timeLocale = {
        dateTime: "%a %e %B %Y %X", date: "%d/%m/%Y", time: "%H:%M:%S", periods: ["am", "pm"],
        days: ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
        shortDays: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        months: ["January", "February", "March", "April", "May", "June", "July", "August", "September",
            "October", "November", "December"],
        shortMonths: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    };

    const views = new Map();
    let theme = {};

    function fetchJSON(url) {
        return fetch(url).then(function (response) {
            if (!response.ok) throw new Error(url + " " + response.status);
            return response.json();
        });
    }

    function exists(url) {
        return fetch(url, { method: "HEAD" }).then(function (r) { return r.ok; }).catch(function () { return false; });
    }

    // CC1: the two found charts (Richard Davies) keep their content; only display fixes ------------------

    const FIXES = {
        // One colour scale for every year, so a colour means the same Gini in 1980 and 2021; country borders
        // (the source's stroke colour "gbp(...)" is invalid); one tooltip line per field; full width
        gini: function (s) {
            const v = s.vconcat ? s.vconcat[0] : s;
            // Its data file starts with a byte-order mark, which Vega 5 keeps in the first column's name, so the
            // lookup by "Country" would find nothing and the map would stay empty: read the file here without it
            const lookup = v.transform.find(function (t) { return t.lookup === "name"; });
            const csv = lookup && lookup.from.data.url;
            const out = Object.assign({ "$schema": s.$schema, params: s.params }, v);
            delete out.title;
            out.width = "container";
            out.mark = Object.assign({}, v.mark, { stroke: "white", strokeWidth: 0.3 });
            // five classes in the project's map blues: neighbouring countries' differences show, and a colour
            // means the same Gini in every year
            out.encoding = Object.assign({}, v.encoding, {
                color: Object.assign({}, v.encoding.color, {
                    scale: { type: "threshold", domain: [0.4, 0.5, 0.6, 0.7],
                             range: ["#d2deee", "#a3bbdc", "#6f93c6", "#3c66a3", "#173c72"] },
                    legend: { orient: "left", direction: "vertical", title: "Gini", format: ".1f", symbolType: "square", symbolSize: 140 }
                }),
                tooltip: { field: "card", type: "nominal" }
            });
            out.transform = out.transform.concat([{ calculate: "{'title': datum.name, 'Gini coefficient': format(datum.Value_N, '.2f')}", as: "card" }]);
            if (!csv) return out;
            return fetch(csv).then(function (r) { return r.text(); }).then(function (text) {
                lookup.from.data = { values: vega.read(text.replace(/^\uFEFF/, ""), { type: "csv" }) };
                return out;
            });
        },
        // Full width, title in the page. Each series' colour comes from the data (percentiles as an ordered blue
        // ramp, the median in red, other views in the page's categorical colours), so the legend lists only the
        // series on screen. Hover cards from the nearest point; dollars written out (the page's currency is £).
        incomes: function (s) {
            delete s.title;
            s.width = "container";
            const L = s.layer[0];
            const names = ["20th", "40th", "60th", "80th", "95th", "Median",
                "All Races", "White, Not Hispanic", "Black", "Asian", "Hispanic (any race)",
                "United States", "Northeast", "Midwest", "South", "West"];
            const colours = ["#a3bbdc", "#7f9fcd", "#5279b5", "#2f5a99", "#173c72", "#c4532d",
                "#16191d", "#1f4e8c", "#c4532d", "#b7a57a", "#5e8c6a",
                "#16191d", "#1f4e8c", "#7f8fa6", "#c4532d", "#b7a57a"];
            const list = function (a) { return "[" + a.map(function (v) { return "'" + v + "'"; }).join(", ") + "]"; };
            L.transform = (L.transform || []).concat([
                { calculate: list(colours) + "[indexof(" + list(names) + ", datum.Series)]", as: "hex" },
                { calculate: "{'title': datum.Series + ', ' + timeFormat(datum.Year, '%Y'), 'Household income': '$' + format(datum.Income, ',.0f')}", as: "card" }
            ]);
            L.encoding.y = Object.assign({}, L.encoding.y, { axis: { title: null } });
            // colours read from the data: the legend's order and the colours both follow the series names (A to Z),
            // so each series keeps its colour in every view
            L.encoding.color = { field: "Series", type: "nominal", title: null, scale: { range: { field: "hex" } } };
            L.encoding.tooltip = { field: "card", type: "nominal" };
            L.mark = { type: "line", strokeWidth: 2 };
            // the dots on the lines as their own layer, sharing the line's colour scale (one colour range, no conflict)
            s.layer.push({
                transform: L.transform,
                mark: { type: "point", filled: true, size: 22, opacity: 1 },
                encoding: { x: L.encoding.x, y: L.encoding.y, color: { field: "Series", type: "nominal" } }
            });
            s.layer.push({
                transform: L.transform,
                params: [{ name: "hp", select: { type: "point", nearest: true, on: "pointerover", clear: "pointerout" } }],
                mark: { type: "point", filled: true, size: 70, color: "#16191d" },
                encoding: { x: L.encoding.x, y: L.encoding.y, tooltip: L.encoding.tooltip,
                            opacity: { condition: { param: "hp", empty: false, value: 0.9 }, value: 0 } }
            });
            return s;
        }
    };

    // Phones: legends and labels that would crowd a narrow chart (each chart says which, in usermeta) ----------

    function setPath(spec, path, value) {
        const keys = path.split(".");
        let o = spec;
        keys.slice(0, -1).forEach(function (k) { o = o[k] = o[k] || {}; });
        o[keys[keys.length - 1]] = value;
    }

    function compact(spec) {
        const meta = spec.usermeta || {};
        if (meta.compactLegend) (function walk(o) {
            if (!o || typeof o !== "object") return;
            if (o.legend && typeof o.legend === "object") Object.assign(o.legend, meta.compactLegend);
            Object.values(o).forEach(walk);
        })(spec.layer || spec.encoding || spec);
        (meta.compactSet || []).forEach(function (entry) { setPath(spec, entry[0], entry[1]); });
        if (meta.compactDropLayers && spec.layer) {
            spec.layer = spec.layer.filter(function (_, i) { return !meta.compactDropLayers.includes(i); });
        }
        return spec;
    }

    // Multi-panel charts (CC4, improved): the panels share the width available; on narrow screens they stack
    function layoutConcat(spec, width) {
        const L = spec.usermeta && spec.usermeta.concatLayout;
        if (!L || !spec.hconcat) return spec;
        if (width < L.stackBelow) {
            spec.vconcat = spec.hconcat;
            delete spec.hconcat;
            // stacked panels keep their relative widths when the chart asks for it, so a shared scale stays shared
            spec.vconcat.forEach(function (panel, i) {
                panel.width = L.stackShares ? Math.floor((width - L.labelRoom) * L.stackShares[i]) : Math.max(200, width - L.labelRoom);
            });
            (L.stackSet || []).forEach(function (entry) { setPath(spec, entry[0], entry[1]); });
        } else {
            const room = width - L.labelRoom - L.gap * (spec.hconcat.length - 1);
            spec.hconcat.forEach(function (panel, i) { panel.width = Math.floor(room * L.shares[i]); });
        }
        return spec;
    }

    // Charts -----------------------------------------------------------------------------------------------------

    function baseHeight(element) {
        const heights = (element.dataset.height || "").split(/\s+/).map(Number).filter(Boolean);
        return narrow.matches && heights[1] ? heights[1] : heights[0];
    }

    function showStatus(element, text) {
        element.innerHTML = "";
        const status = document.createElement("div");
        status.className = "chart-status";
        status.textContent = text;
        element.appendChild(status);
    }

    // CC9b: the chart head names the indicator chosen in the menu
    function followIndicator(element, view, spec) {
        const meta = spec.usermeta || {};
        const figure = element.closest("figure");
        const title = figure && figure.querySelector(".chart-title");
        const subtitle = figure && figure.querySelector(".chart-subtitle");
        function update(value) {
            if (title && meta.titles && meta.titles[value]) title.textContent = meta.titles[value];
            if (subtitle && meta.units && meta.units[value]) subtitle.textContent = meta.units[value] + "; choose an indicator and an authority";
        }
        update(view.signal("indicator"));
        view.addSignalListener("indicator", function (name, value) { update(value); });
    }

    function embed(element) {
        const needs = element.dataset.needs;
        return (needs ? exists(needs) : Promise.resolve(true)).then(function (ready) {
            if (!ready) {
                console.info(element.id + ": waiting for " + needs);      // the placeholder stays
                return;
            }
            const height = baseHeight(element);
            if (height) element.style.minHeight = height + "px";
            showStatus(element, "Loading chart…");
            return fetchJSON(element.dataset.spec)
                .then(function (spec) {
                    const fix = FIXES[element.dataset.fix];
                    return fix ? fix(spec) : spec;
                })
                .then(function (spec) {
                    const single = !spec.hconcat && !spec.vconcat && !spec.concat;
                    if (height && single && (typeof spec.height === "number" || spec.height === undefined)) spec.height = height;
                    const below = spec.usermeta && spec.usermeta.compactBelow;
                    if (narrow.matches || (below && element.clientWidth < below)) spec = compact(spec);
                    spec = layoutConcat(spec, element.clientWidth);
                    return vegaEmbed(element, spec, {
                        renderer: element.dataset.renderer || "svg",
                        actions: false,
                        config: theme,
                        formatLocale: numberLocale,
                        timeFormatLocale: timeLocale,
                        tooltip: { theme: "custom" }
                    }).then(function (result) {
                        element.style.minHeight = "";
                        views.set(element.id, result.view);
                        // a tap on a chart's empty space hides an open tooltip
                        result.view.addEventListener("touchstart", function (event, item) {
                            if (!item || item.tooltip == null) hideTooltips();
                        });
                        if (spec.usermeta && spec.usermeta.titles) followIndicator(element, result.view, spec);
                    });
                })
                .catch(function (error) {
                    showStatus(element, "This chart could not be drawn.");
                    console.error(element.id, error);
                });
        });
    }

    function lazyLoad() {
        const charts = Array.from(document.querySelectorAll(".chart-body[data-spec]"));
        if (typeof IntersectionObserver !== "function") {
            charts.forEach(embed);
            return;
        }
        const observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) return;
                observer.unobserve(entry.target);
                embed(entry.target);
            });
        }, { rootMargin: "600px 0px" });
        charts.forEach(function (chart) { observer.observe(chart); });
    }

    // CC4: the screenshot of the original chart appears once img/cc4_original.png exists
    function showImages() {
        document.querySelectorAll("[data-image]").forEach(function (slot) {
            exists(slot.dataset.image).then(function (ok) {
                if (!ok) return;
                const img = document.createElement("img");
                img.src = slot.dataset.image;
                img.alt = slot.dataset.alt || "";
                img.style.cssText = "display:block;width:100%;height:auto";
                slot.replaceWith(img);
            });
        });
    }

    function saveImage(id) {
        const view = views.get(id);
        if (!view) return;
        view.toImageURL("png", 2).then(function (url) {
            const link = document.createElement("a");
            link.href = url;
            link.download = id + ".png";
            document.body.appendChild(link);
            link.click();
            link.remove();
        });
    }

    // Page: reading progress, the section in view, tooltips on touch screens -----------------------------------

    function trackProgress() {
        const bar = document.querySelector(".progress");
        if (!bar) return;
        let pending = false;
        function update() {
            pending = false;
            const max = document.documentElement.scrollHeight - window.innerHeight;
            bar.style.setProperty("--progress", max > 0 ? Math.min(1, window.scrollY / max) : 0);
        }
        window.addEventListener("scroll", function () {
            if (pending) return;
            pending = true;
            requestAnimationFrame(update);
        }, { passive: true });
        update();
    }

    function trackSections() {
        const links = Array.from(document.querySelectorAll(".contents a[href^='#']"));
        if (!links.length || typeof IntersectionObserver !== "function") return;
        const byId = new Map(links.map(function (a) { return [a.hash.slice(1), a]; }));
        const observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) return;
                links.forEach(function (a) { a.removeAttribute("aria-current"); });
                const link = byId.get(entry.target.id);
                if (link) link.setAttribute("aria-current", "true");
            });
        }, { rootMargin: "-8% 0px -80% 0px" });
        byId.forEach(function (_, id) {
            const section = document.getElementById(id);
            if (section) observer.observe(section);
        });
    }

    // Tooltips on touch screens: a tap shows one like a mouse hover, but lifting the finger sends no
    // "pointer left" event, so the tooltip would stay. It is hidden on scroll, on a tap outside a chart,
    // on a tap on a chart's empty space (above), and with Escape. A mouse keeps its usual behaviour.
    function hideTooltips() {
        document.querySelectorAll("#vg-tooltip-element.visible, .vg-tooltip.visible").forEach(function (tip) {
            tip.classList.remove("visible");
        });
    }

    function wireTooltipDismissal() {
        let pending = false;
        window.addEventListener("scroll", function () {
            if (pending) return;
            pending = true;
            requestAnimationFrame(function () {
                pending = false;
                hideTooltips();
            });
        }, { passive: true });
        document.addEventListener("pointerdown", function (event) {
            if (event.pointerType !== "mouse" && !event.target.closest(".chart-body")) hideTooltips();
        }, { passive: true });
        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") hideTooltips();
        });
    }

    function wireSaveButtons() {
        document.addEventListener("click", function (event) {
            const button = event.target.closest("[data-save]");
            if (button) saveImage(button.dataset.save);
        });
    }

    // For the author, in the browser console: text still to write, and the brief's word limits
    function checkText() {
        const drafts = document.querySelectorAll(".draft");
        if (drafts.length) console.warn(drafts.length + " passages still marked as draft:",
            Array.from(drafts).map(function (d) { return d.textContent.trim(); }).join(" "));
        document.querySelectorAll("[data-maxwords]").forEach(function (el) {
            const words = el.textContent.trim().split(/\s+/).filter(Boolean).length;
            if (words > Number(el.dataset.maxwords)) console.warn(words + " words (limit " + el.dataset.maxwords + "):", el.textContent.trim());
        });
    }

    function init() {
        trackProgress();
        trackSections();
        wireTooltipDismissal();
        wireSaveButtons();
        showImages();
        checkText();
        fetchJSON(THEME).catch(function () { return {}; }).then(function (loaded) {
            theme = loaded;
            lazyLoad();
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
