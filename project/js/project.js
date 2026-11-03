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
