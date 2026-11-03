/* Project page: loads the Vega-Lite charts, wires their controls, scroll steps and headline numbers */

(function () {
    "use strict";

    const THEME = "project/charts/theme.json";
    const SUMMARY = "project/data/summary.json";
    const COUNCILS = "project/data/councils.csv";
    const narrow = window.matchMedia("(max-width: 40rem)");

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
    const queued = new Map();
    let theme = {};
    let summary = null;
    let councils = [];

    function fetchJSON(url) {
        return fetch(url).then(function (response) {
            if (!response.ok) throw new Error(url + " " + response.status);
            return response.json();
        });
    }

    // Numbers in page text ------------------------------------------------------------

    function formatValue(value, kind) {
        const number = Number(value);
        switch (kind) {
            case "pct0": return (100 * number).toFixed(0) + "%";
            case "pct1": return (100 * number).toFixed(1) + "%";
            case "pct2": return (100 * number).toFixed(2) + "%";
            case "gbp": return "£" + Math.round(number).toLocaleString("en-GB");
            case "gbpk": return number >= 1e6
                ? "£" + Number((number / 1e6).toFixed(2)) + "m"
                : "£" + Math.round(number / 1000) + "k";
            case "int": return Math.round(number).toLocaleString("en-GB");
            case "thousands": return (Math.round(number / 1000) * 1000).toLocaleString("en-GB");
            case "millions": return (number / 1e6).toFixed(1) + "m";
            case "millions2": return (number / 1e6).toFixed(2) + "m";
            case "times": return number.toFixed(1) + "×";
            case "times0": return Math.round(number) + "×";
            case "year": return String(value).slice(0, 4);
            case "month": {
                const [year, month] = String(value).split("-").map(Number);
                return timeLocale.months[month - 1] + " " + year;
            }
            case "date": {
                const date = new Date(value);
                return date.getUTCDate() + " " + timeLocale.months[date.getUTCMonth()] + " " + date.getUTCFullYear();
            }
            default: return String(value);
        }
    }

    function lookup(path, source) {
        return path.split(".").reduce(function (node, key) {
            return node == null ? undefined : node[key];
        }, source);
    }

    // Numbers in the text: <span data-stat="facts.fig1.cheap_rate" data-format="pct2">1.49%</span>.
    // A key that summary.json lacks keeps its typed value and is reported, so typos show up at once.
    function fillStats() {
        const missing = [];
        document.querySelectorAll("[data-stat]").forEach(function (element) {
            const value = lookup(element.dataset.stat, summary);
            if (value == null) {
                missing.push(element.dataset.stat);
                return;
            }
            element.textContent = formatValue(value, element.dataset.format);
            if (element.tagName === "TIME") element.dateTime = String(value);
        });
        if (missing.length) console.warn("No value in summary.json for: " + missing.join(", "));
    }

    // Charts ------------------------------------------------------------------------------

    // Space a chart needs beyond its plot (axes, axis titles, padding): estimated until it is drawn, then measured
    const AXIS = 56;

    function extraFor(element) {
        return Number(element.dataset.extra) || AXIS;
    }

    function baseHeight(element) {
        const heights = (element.dataset.height || "").split(/\s+/).map(Number).filter(Boolean);
        return narrow.matches && heights[1] ? heights[1] : heights[0];
    }

    function navHeight() {
        const nav = document.querySelector(".contents");
        return nav ? nav.getBoundingClientRect().height : 0;
    }

    function outerHeight(element) {
        if (!element) return 0;
        const style = getComputedStyle(element);
        return element.getBoundingClientRect().height + parseFloat(style.marginTop) + parseFloat(style.marginBottom);
    }

    // Figure 1: chart, controls and, where there is room, the title must fit in the window together.
    // On short windows and phones the title scrolls away first (--head-h), so the chart keeps its size.
    function layoutScrolly(section) {
        const graphic = section.querySelector(".scrolly-graphic");
        const head = graphic.querySelector(".chart-head");
        const chart = graphic.querySelector(".chart-body");
        const room = window.innerHeight - navHeight() - 28;
        const fixed = outerHeight(graphic.querySelector(".controls")) + extraFor(chart);
        let height = room - outerHeight(head) - fixed;
        const titleScrolls = narrow.matches || height < 320;
        if (titleScrolls) height = room - fixed;
        if (narrow.matches) height = Math.min(height, Math.round(0.45 * window.innerHeight));
        height = Math.round(Math.max(220, Math.min(baseHeight(chart), height)));
        section.classList.toggle("is-static", window.innerHeight < 480);
        graphic.style.setProperty("--head-h", titleScrolls ? outerHeight(head) + "px" : "0px");
        return height;
    }

    function heightFor(element) {
        if (element.dataset.fit === "scrolly") return layoutScrolly(element.closest("[data-scrolly]"));
        let height = baseHeight(element);
        if (element.dataset.fit === "screen") {
            height = Math.max(300, Math.min(height, window.innerHeight - navHeight() - 90));
        }
        return height;
    }

    function showStatus(element, text) {
        element.innerHTML = "";
        const status = document.createElement("div");
        status.className = "chart-status";
        status.textContent = text;
        element.appendChild(status);
    }

    function embed(element) {
        const id = element.id;
        const reserve = heightFor(element);
        if (reserve) element.style.minHeight = reserve + extraFor(element) + "px";
        showStatus(element, "Loading chart…");
        return fetchJSON(element.dataset.spec)
            .then(function (spec) {
                const height = heightFor(element);
                if (height && typeof spec.height === "number") spec.height = height;
                return vegaEmbed(element, spec, {
                    renderer: element.dataset.renderer || "svg",
                    actions: false,
                    config: theme,
                    formatLocale: numberLocale,
                    timeFormatLocale: timeLocale,
                    tooltip: { theme: "custom" }
                });
            })
            .then(function (result) {
                element.style.minHeight = "";
                views.set(id, result.view);
                element.dataset.extra = Math.ceil(element.getBoundingClientRect().height - result.view.height());
                if (element.dataset.fit) {
                    const height = heightFor(element);
                    if (height !== result.view.height()) return result.view.height(height).runAsync().then(function () {
                        return result;
                    });
                }
                return result;
            })
            .then(function () {
                const section = element.closest("[data-scrolly]");
                if (section) section.dispatchEvent(new CustomEvent("relayout"));
                const waiting = queued.get(id) || {};
                Object.keys(waiting).forEach(function (name) {
                    setSignal(id, name, waiting[name]);
                });
                queued.delete(id);
            })
            .catch(function (error) {
                showStatus(element, "This chart could not be drawn. Its data may not have been built yet.");
                console.error(id, error);
            });
    }

    function setSignal(id, name, value) {
        const view = views.get(id);
        if (!view) {
            queued.set(id, Object.assign(queued.get(id) || {}, { [name]: value }));
            return;
        }
        try {
            view.signal(name, value).runAsync();
        } catch (error) {
            console.warn(id + ": no parameter " + name, error);
        }
    }

    function lazyLoad() {
        const charts = Array.from(document.querySelectorAll(".chart-body[data-spec]"));
        if (!("IntersectionObserver" in window)) {
            charts.forEach(embed);
            return;
        }
        const observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) return;
                observer.unobserve(entry.target);
                embed(entry.target);
            });
        }, { rootMargin: "700px 0px" });
        charts.forEach(function (chart) {
            observer.observe(chart);
        });
    }

    function refit() {
        document.querySelectorAll("[data-scrolly]").forEach(function (section) {
            layoutScrolly(section);
            section.dispatchEvent(new CustomEvent("relayout"));
        });
        views.forEach(function (view, id) {
            const height = heightFor(document.getElementById(id));
            if (height && height !== view.height()) view.height(height).runAsync();
        });
    }

    function refitOnResize() {
        let timer = 0;
        window.addEventListener("resize", function () {
            clearTimeout(timer);
            timer = setTimeout(refit, 150);
        });
        narrow.addEventListener("change", refit);
    }

    // Controls ------------------------------------------------------------------------

    function targets(element) {
        return (element.dataset.chart || "").split(/\s+/).filter(Boolean);
    }

    function parse(value, type) {
        return type === "number" ? Number(value) : value;
    }

    function press(group, value) {
        if (!group) return;
        group.querySelectorAll("button").forEach(function (button) {
            button.setAttribute("aria-pressed", String(button.dataset.value === String(value)));
        });
    }

    function wireControls() {
        document.addEventListener("click", function (event) {
            const button = event.target.closest(".segmented button");
            if (button) {
                const group = button.closest(".segmented");
                press(group, button.dataset.value);
                targets(group).forEach(function (id) {
                    setSignal(id, group.dataset.signal, parse(button.dataset.value, group.dataset.type));
                });
                group.dispatchEvent(new CustomEvent("choice", { bubbles: true, detail: button.dataset.value }));
                return;
            }
            const save = event.target.closest("[data-save]");
            if (save) saveImage(save.dataset.save);
        });

        document.querySelectorAll("select[data-signal]").forEach(function (select) {
            select.addEventListener("change", function () {
                targets(select).forEach(function (id) {
                    setSignal(id, select.dataset.signal, parse(select.value, select.dataset.type));
                });
            });
        });
    }

    function wireJumps() {
        document.addEventListener("click", function (event) {
            const link = event.target.closest('a[href^="#"]');
            const target = link && document.getElementById(link.hash.slice(1));
            const body = target && target.querySelector(".scrolly-body");
            if (!body) return;
            const graphic = body.querySelector(".scrolly-graphic");
            const titleHeight = parseFloat(getComputedStyle(graphic).getPropertyValue("--head-h")) || 0;
            if (!titleHeight || target.classList.contains("is-static")) return;
            event.preventDefault();
            const top = body.getBoundingClientRect().top + window.scrollY + titleHeight - navHeight() - 12;
            window.scrollTo(0, Math.max(0, Math.round(top)));
            history.pushState(null, "", link.hash);
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

    // Council search and pickers, filled from councils.csv ----------------------------------

    function loadCouncils() {
        return fetch(COUNCILS)
            .then(function (response) {
                if (!response.ok) throw new Error(COUNCILS + " " + response.status);
                return response.text();
            })
            .then(function (text) {
                return vega.read(text, { type: "csv", parse: "auto" })
                    .filter(function (row) { return row.lad && row.name; })
                    .sort(function (a, b) { return a.name.localeCompare(b.name, "en-GB"); });
            });
    }

    function wireCouncils() {
        const list = document.getElementById("council-list");
        if (list) {
            councils.forEach(function (council) {
                const option = document.createElement("option");
                option.value = council.name;
                list.appendChild(option);
            });
        }

        const byName = new Map(councils.map(function (council) {
            return [council.name.toLowerCase(), council.lad];
        }));

        document.querySelectorAll("input[data-council-search]").forEach(function (input) {
            const apply = function () {
                const name = input.value.trim().toLowerCase();
                const code = byName.get(name);
                if (code || name === "") {
                    targets(input).forEach(function (id) {
                        setSignal(id, "council", code || "");
                    });
                }
            };
            input.addEventListener("input", apply);
            input.addEventListener("change", apply);
        });

        document.querySelectorAll("select[data-councils]").forEach(function (select) {
            const chosen = select.dataset.default;
            councils.forEach(function (council) {
                const option = new Option(council.name, council.lad, false, council.lad === chosen);
                select.appendChild(option);
            });
            targets(select).forEach(function (id) {
                setSignal(id, select.dataset.signal, select.value);
            });
        });
    }

    // Your council: chosen by name or found from the reader's location ------------------------

    const NEIGHBOURS = "project/geo/neighbours-2025.json";
    const BOUNDARIES = "project/geo/lad-2025-map.geojson";
    const MAP_CHARTS = ["chart-3", "chart-6"];
    let neighbourMap = null;
    let boundaries = null;

    // Latitude and longitude (WGS84) to British National Grid metres, following the Ordnance
    // Survey's guide: Helmert transformation to OSGB36, then the national Transverse Mercator.
    // Accurate to a few metres, far finer than council boundaries need.
    function toNationalGrid(lat, lon) {
        const rad = Math.PI / 180;
        let a = 6378137, b = 6356752.3142, e2 = 1 - (b * b) / (a * a);
        let phi = lat * rad, lambda = lon * rad;
        let nu = a / Math.sqrt(1 - e2 * Math.sin(phi) ** 2);
        const x1 = nu * Math.cos(phi) * Math.cos(lambda);
        const y1 = nu * Math.cos(phi) * Math.sin(lambda);
        const z1 = (1 - e2) * nu * Math.sin(phi);

        const tx = -446.448, ty = 125.157, tz = -542.060, s = 20.4894e-6;
        const rx = -0.1502 / 3600 * rad, ry = -0.2470 / 3600 * rad, rz = -0.8421 / 3600 * rad;
        const x2 = tx + (1 + s) * x1 - rz * y1 + ry * z1;
        const y2 = ty + rz * x1 + (1 + s) * y1 - rx * z1;
        const z2 = tz - ry * x1 + rx * y1 + (1 + s) * z1;

        a = 6377563.396; b = 6356256.909; e2 = 1 - (b * b) / (a * a);
        const p = Math.sqrt(x2 * x2 + y2 * y2);
        phi = Math.atan2(z2, p * (1 - e2));
        for (let i = 0; i < 10; i++) {
            nu = a / Math.sqrt(1 - e2 * Math.sin(phi) ** 2);
            phi = Math.atan2(z2 + e2 * nu * Math.sin(phi), p);
        }
        lambda = Math.atan2(y2, x2);

        const F0 = 0.9996012717, phi0 = 49 * rad, lambda0 = -2 * rad;
        const n = (a - b) / (a + b);
        const sin = Math.sin(phi), cos = Math.cos(phi), tan2 = Math.tan(phi) ** 2;
        nu = a * F0 / Math.sqrt(1 - e2 * sin * sin);
        const rho = a * F0 * (1 - e2) / Math.pow(1 - e2 * sin * sin, 1.5);
        const eta2 = nu / rho - 1;
        const d = phi - phi0, t = phi + phi0;
        const M = b * F0 * ((1 + n + 1.25 * n ** 2 + 1.25 * n ** 3) * d
            - (3 * n + 3 * n ** 2 + 2.625 * n ** 3) * Math.sin(d) * Math.cos(t)
            + (1.875 * n ** 2 + 1.875 * n ** 3) * Math.sin(2 * d) * Math.cos(2 * t)
            - (35 / 24) * n ** 3 * Math.sin(3 * d) * Math.cos(3 * t));
        const L = lambda - lambda0;
        const north = M - 100000 + nu / 2 * sin * cos * L ** 2
            + nu / 24 * sin * cos ** 3 * (5 - tan2 + 9 * eta2) * L ** 4
            + nu / 720 * sin * cos ** 5 * (61 - 58 * tan2 + tan2 ** 2) * L ** 6;
        const east = 400000 + nu * cos * L
            + nu / 6 * cos ** 3 * (nu / rho - tan2) * L ** 3
            + nu / 120 * cos ** 5 * (5 - 18 * tan2 + tan2 ** 2 + 14 * eta2 - 58 * tan2 * eta2) * L ** 5;
        return [east, north];
    }

    function polygonsOf(geometry) {
        return geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
    }

    function inRing(x, y, ring) {
        let inside = false;
        for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
            const [xi, yi] = ring[i], [xj, yj] = ring[j];
            if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
        }
        return inside;
    }

    // The council containing a point; failing that, the nearest within 3 km, for readers on a
    // riverbank or the coast, where generalised boundaries stop short of the water's edge
    function councilAt(x, y) {
        let nearest = null, best = 3000;
        for (const feature of boundaries.features) {
            for (const polygon of polygonsOf(feature.geometry)) {
                if (inRing(x, y, polygon[0]) && !polygon.slice(1).some(function (hole) { return inRing(x, y, hole); })) {
                    return feature.properties.lad;
                }
                for (const [px, py] of polygon[0]) {
                    const distance = Math.hypot(px - x, py - y);
                    if (distance < best) { best = distance; nearest = feature.properties.lad; }
                }
            }
        }
        return nearest;
    }

    function ordinal(n) {
        const ends = ["th", "st", "nd", "rd"], v = n % 100;
        return n + (ends[(v - 20) % 10] || ends[v] || ends[0]);
    }

    function element(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text != null) node.textContent = text;
        return node;
    }

    function showCouncilMessage(text) {
        const box = document.querySelector("[data-council-result]");
        box.hidden = false;
        box.innerHTML = "";
        box.appendChild(element("p", "council-message", text));
    }

    function showCouncil(code) {
        const box = document.querySelector("[data-council-result]");
        const council = councils.find(function (row) { return row.lad === code; });
        if (!box || !council || !isFinite(council.rate_mix)) {
            showCouncilMessage("No rate is available for that council.");
            return;
        }
        const ranked = councils.filter(function (row) { return isFinite(row.rate_mix); })
            .sort(function (x, y) { return y.rate_mix - x.rate_mix; });
        const rank = ranked.findIndex(function (row) { return row.lad === code; }) + 1;
        const fromBottom = ranked.length - rank + 1;
        const place = rank <= fromBottom
            ? (rank === 1 ? "highest" : ordinal(rank) + " highest")
            : (fromBottom === 1 ? "lowest" : ordinal(fromBottom) + " lowest");

        box.hidden = false;
        box.innerHTML = "";

        // 1. The council's rate, its rank and England's rate in one line; its bill and value below
        box.appendChild(element("p", "council-name", council.name));
        const rate = element("p", "council-rate");
        rate.appendChild(element("strong", null, formatValue(council.rate_mix, "pct2")));
        rate.appendChild(document.createTextNode(" of home value a year · " + place + " of " + ranked.length +
            " councils (England " + formatValue(summary.england.rate_mix, "pct2") + ")"));
        box.appendChild(rate);
        box.appendChild(element("p", "council-detail", "Average bill " + formatValue(council.bill, "gbp") +
            " before discounts, on an average home worth " + formatValue(council.value, "gbp")));

        // 2. Next door: the council and its eight largest neighbours, by rate
        const nearby = ((neighbourMap && neighbourMap[code]) || []).map(function (lad) {
            return councils.find(function (row) { return row.lad === lad; });
        }).filter(function (row) { return row && isFinite(row.rate_mix); })
            .sort(function (x, y) { return y.dwellings - x.dwellings; })
            .slice(0, 8);
        const rows = [council].concat(nearby).sort(function (x, y) { return y.rate_mix - x.rate_mix; });
        if (rows.length > 1) {
            const top = rows[0].rate_mix;
            box.appendChild(element("p", "council-neighbours-title", "Next door"));
            const list = element("ul", "council-neighbours");
            rows.forEach(function (row) {
                const item = element("li", row.lad === code ? "is-self" : null);
                item.appendChild(element("span", "name", row.name));
                const bar = element("span", "bar");
                bar.style.setProperty("--w", (100 * row.rate_mix / top).toFixed(1) + "%");
                item.appendChild(bar);
                item.appendChild(element("span", "rate", formatValue(row.rate_mix, "pct2")));
                list.appendChild(item);
            });
            box.appendChild(list);
        } else if (neighbourMap) {
            box.appendChild(element("p", "council-detail", "No council shares a border with it."));
        }

        // 3. The same council at the one flat rate on today's value that raises today's total for England;
        //    both bills before discounts, so like is compared with like
        const neutral = summary.england.revenue_neutral_rate;
        if (isFinite(neutral) && isFinite(council.value) && isFinite(council.bill) && council.bill > 0) {
            const flat = neutral * council.value;
            const ratio = flat / council.bill;
            const change = ratio >= 2 ? ratio.toFixed(1) + " times today’s"
                : ratio >= 1 ? formatValue(ratio - 1, "pct0") + " more than today"
                : formatValue(1 - ratio, "pct0") + " less than today";
            const line = element("p", "council-flat");
            line.appendChild(document.createTextNode("At a flat " + formatValue(neutral, "pct2") +
                " of value, which raises the same total for England, the average bill here would be about "));
            line.appendChild(element("b", null, formatValue(Math.round(flat / 10) * 10, "gbp")));
            line.appendChild(document.createTextNode(": " + change + "."));
            box.appendChild(line);
        }

        const links = element("p", "council-links");
        const toMap = element("a", null, "See it on the map");
        toMap.href = "#figure-3";
        const toFlat = element("a", null, "Try other rates");
        toFlat.href = "#figure-6";
        links.appendChild(toMap);
        links.appendChild(document.createTextNode(" · "));
        links.appendChild(toFlat);
        box.appendChild(links);
    }

    function chooseCouncil(code) {
        const council = councils.find(function (row) { return row.lad === code; });
        if (!council) return;
        const input = document.querySelector("input[data-your-council]");
        if (input) input.value = council.name;
        // pick the council out on both maps, and show it in their search boxes
        MAP_CHARTS.forEach(function (id) { setSignal(id, "council", code); });
        document.querySelectorAll("input[data-council-search]").forEach(function (search) {
            if (targets(search).some(function (id) { return MAP_CHARTS.indexOf(id) >= 0; })) search.value = council.name;
        });
        const show = function () { showCouncil(code); };
        if (neighbourMap) {
            show();
        } else {
            fetchJSON(NEIGHBOURS).then(function (map) { neighbourMap = map; }).catch(function () { neighbourMap = {}; }).then(show);
        }
    }

    function locate(button) {
        if (!("geolocation" in navigator)) {
            showCouncilMessage("This browser cannot share a location. Type your council instead.");
            return;
        }
        button.setAttribute("aria-busy", "true");
        showCouncilMessage("Finding your council…");
        const loaded = boundaries ? Promise.resolve(boundaries)
            : fetchJSON(BOUNDARIES).then(function (geo) { boundaries = geo; return geo; });
        navigator.geolocation.getCurrentPosition(function (position) {
            loaded.then(function () {
                const [east, north] = toNationalGrid(position.coords.latitude, position.coords.longitude);
                const code = councilAt(east, north);
                if (code) chooseCouncil(code);
                else showCouncilMessage("That location is outside England. Type your council instead.");
            }).catch(function () {
                showCouncilMessage("The council map could not be loaded. Type your council instead.");
            }).then(function () { button.removeAttribute("aria-busy"); });
        }, function (error) {
            button.removeAttribute("aria-busy");
            showCouncilMessage(error.code === 1 ? "Location access was declined. Type your council instead."
                : "Your location could not be found. Type your council instead.");
        }, { enableHighAccuracy: false, timeout: 15000, maximumAge: 600000 });
    }

    function wireYourCouncil() {
        const input = document.querySelector("input[data-your-council]");
        const button = document.querySelector("[data-locate]");
        if (!input) return;
        const byName = new Map(councils.map(function (row) { return [row.name.toLowerCase(), row.lad]; }));
        const pick = function () {
            const code = byName.get(input.value.trim().toLowerCase());
            if (code) chooseCouncil(code);
        };
        input.addEventListener("input", pick);
        input.addEventListener("change", pick);
        if (button) button.addEventListener("click", function () { locate(button); });
    }

    // Flat-tax slider -----------------------------------------------------------------------

    function wireSlider(slider) {
        const input = slider.querySelector("input[type=range]");
        const output = slider.querySelector("output");
        const note = slider.querySelector("[data-revenue]");
        const neutral = summary.england.revenue_neutral_rate;
        const min = Number(input.min);
        const max = Number(input.max);
        let local = false;
        let pinned = null;

        slider.querySelectorAll(".slider-marks button").forEach(function (mark) {
            const rate = mark.dataset.rate === "neutral" ? neutral : Number(mark.dataset.rate);
            mark.dataset.value = rate;
            mark.style.setProperty("--at", (100 * (rate - min) / (max - min)).toFixed(2) + "%");
            if (mark.dataset.rate === "neutral") mark.textContent = formatValue(rate, "pct2");
            mark.addEventListener("click", function () {
                input.value = rate;
                pinned = rate;
                update();
            });
        });

        function update() {
            const value = Number(input.value);
            const rate = pinned !== null && Math.abs(pinned - value) < 1e-5 ? pinned : value;
            input.style.setProperty("--fill", (100 * (rate - min) / (max - min)).toFixed(2) + "%");
            if (local) {
                output.textContent = "Varies";
                note.textContent = "Each council sets the rate that raises its current total";
            } else {
                output.textContent = formatValue(rate, "pct2");
                note.textContent = "Raises " + formatValue(rate / neutral, "pct0") + " of today’s total";
            }
            input.disabled = local;
            targets(input).forEach(function (id) {
                setSignal(id, "rate", rate);
            });
        }

        let frame = 0;
        input.addEventListener("input", function () {
            pinned = null;
            cancelAnimationFrame(frame);
            frame = requestAnimationFrame(update);
        });

        const mode = document.querySelector('.segmented[data-signal="mode"]');
        if (mode) {
            mode.addEventListener("choice", function (event) {
                local = event.detail === "local";
                update();
            });
        }
        update();
    }

    // Scroll-driven steps -----------------------------------------------------------------

    // Where a note switches the chart: mid-window beside the chart; on phones, in the strip
    // left visible below the pinned chart, so a note is never read out of sight
    function stepBand(section) {
        const height = window.innerHeight;
        if (!narrow.matches || section.classList.contains("is-static")) {
            return "-50% 0px -40% 0px";
        }
        const pinned = section.querySelector(".scrolly-graphic").getBoundingClientRect();
        const below = Math.min(height - 40, navHeight() + 12 + pinned.height - outerHeight(section.querySelector(".chart-head")));
        const top = Math.round(below + 0.2 * (height - below));
        const bottom = Math.round(below + 0.6 * (height - below));
        section.dataset.band = top + " " + bottom;
        return -top + "px 0px " + -(height - bottom) + "px 0px";
    }

    function wireScrolly(section) {
        const id = section.dataset.scrolly;
        const steps = Array.from(section.querySelectorAll(".step"));
        const group = section.querySelector('.segmented[data-signal="step"]');

        function activate(step) {
            steps.forEach(function (other) {
                other.classList.toggle("is-active", other === step);
            });
            setSignal(id, "step", Number(step.dataset.step));
            press(group, step.dataset.step);
        }

        let observer = null;
        function observe() {
            if (observer) observer.disconnect();
            delete section.dataset.band;
            // watch the cards, not their tall slots: neighbouring slots overlap the band at the same time
            observer = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) activate(entry.target.closest(".step"));
                });
            }, { rootMargin: stepBand(section) });
            steps.forEach(function (step) {
                observer.observe(step.firstElementChild || step);
            });
        }

        layoutScrolly(section);
        if (!steps.length || !("IntersectionObserver" in window)) return;
        activate(steps[0]);
        observe();
        section.addEventListener("relayout", observe);
    }

    // Reading progress and current section -------------------------------------------------

    function trackProgress() {
        const bar = document.querySelector(".progress");
        if (!bar) return;
        let frame = 0;
        const update = function () {
            const height = document.documentElement.scrollHeight - window.innerHeight;
            bar.style.setProperty("--progress", height > 0 ? Math.min(1, window.scrollY / height).toFixed(4) : 0);
            frame = 0;
        };
        window.addEventListener("scroll", function () {
            if (!frame) frame = requestAnimationFrame(update);
        }, { passive: true });
        update();
    }

    // Bring the current link into view inside the bar, which scrolls sideways on phones.
    // Only the bar is scrolled: asking the browser to reveal the link would, in Firefox,
    // also scroll the page back to where the pinned bar started.
    function centreInBar(link) {
        const list = link.closest("ol");
        if (!list || list.scrollWidth <= list.clientWidth) return;
        const bar = list.getBoundingClientRect();
        const box = link.getBoundingClientRect();
        const left = list.scrollLeft + box.left - bar.left - (bar.width - box.width) / 2;
        list.scrollTo({ left: Math.max(0, left), behavior: "smooth" });
    }

    function trackSections() {
        const links = Array.from(document.querySelectorAll(".contents a[href^='#']"));
        const sections = links.map(function (link) {
            return document.getElementById(link.hash.slice(1));
        }).filter(Boolean);
        if (!sections.length || !("IntersectionObserver" in window)) return;
        const observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) return;
                links.forEach(function (link) {
                    const current = link.hash === "#" + entry.target.id;
                    if (current) {
                        link.setAttribute("aria-current", "true");
                        centreInBar(link);
                    } else {
                        link.removeAttribute("aria-current");
                    }
                });
            });
        }, { rootMargin: "-8% 0px -80% 0px" });
        sections.forEach(function (section) {
            observer.observe(section);
        });
    }

    // Start ------------------------------------------------------------------------------

    function init() {
        trackProgress();
        trackSections();
        wireControls();
        wireJumps();
        refitOnResize();

        Promise.all([
            fetchJSON(THEME).catch(function () { return {}; }),
            fetchJSON(SUMMARY).catch(function () { return null; })
        ]).then(function (loaded) {
            theme = loaded[0];
            summary = loaded[1];
            if (!summary) {
                document.querySelectorAll(".chart-body[data-spec]").forEach(function (element) {
                    showStatus(element, "Data not built yet. Run the “Update project data” workflow on GitHub.");
                });
                return;
            }
            fillStats();
            document.querySelectorAll("[data-scrolly]").forEach(wireScrolly);
            return loadCouncils()
                .then(function (rows) {
                    councils = rows;
                    wireCouncils();
                    wireYourCouncil();
                })
                .catch(function (error) {
                    console.error(error);
                })
                .then(function () {
                    document.querySelectorAll(".slider").forEach(wireSlider);
                    lazyLoad();
                });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
