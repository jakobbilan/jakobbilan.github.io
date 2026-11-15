# PP434 portfolio kit: tax progressivity and inequality

Copy everything into the root of your GitHub Pages repository (next to `index.html`). Paths are relative: keep
`portfolio.html`, `DevolutionDashboard.html`, `charts/`, `data/`, `css/`, `img/` and `notebooks/` side by side.

```
portfolio.html              the graded portfolio page, one section per coding challenge
DevolutionDashboard.html    CC6, the separate page the brief asks for (exact file name)
css/portfolio.css           shared styles
charts/                     8 Vega-Lite 6 specifications
data/                       data files; two more are written by notebooks (see step 2)
notebooks/                  Colab notebooks: CC2 chart 1 (WID download), CC5 scraper, CC6 loop (also writes the CC9 table), CC7 points
img/                        CC4: save the original chart here as cc4_original.png
```

Text on the pages is a set of bracketed placeholders ([Headline], [Note], [Policy topic], ...). Suggested text for each
one is in the separate Word file, *PP434 portfolio - page draft.docx*.

## Set-up

1. Copy the files and open `portfolio.html` with Live Server. Every chart except CC2 chart 1 and the CC5 scraper chart
   works straight away; those two keep their placeholder until their data exist.
2. In Colab, run `notebooks/cc2a_wid_download.ipynb` and `notebooks/cc5_scraper_tax_rates.ipynb`; upload the CSV each one
   writes to `data/`.
3. Share the CC5 and CC6 notebooks in Colab as "Anyone with the link" and use the links for the two
   `[Link to the Colab notebook]` anchors (set the `href`).
4. In `DevolutionDashboard.html`, check `RAW_BASE` (user `jakobbilan`, repository `jakobbilan.github.io`, branch `main`).
   Once the six JSON files are pushed, the charts load from those raw links; before that they use the local folder.
5. Replace the placeholders. The browser console lists any left and warns if a text marked `data-maxwords="25"`
   (CC3 topic and comment, CC4 explanation, CC5 comment) runs over 25 words.
6. CC4 fills itself in once these exist: `img/cc4_original.png`, `charts/cc4a_replica.json`, `charts/cc4b_improved.json`.
   CC8 does the same with `charts/cc8a_prices.json` and `charts/cc8b_prices.json` (built from the class AutoCPI data).
   CC10 is in the page but hidden (`hidden` on its section and contents link): the new brief sets nine tasks.
7. Commit, push, and check the live pages, including on a phone.

## What each chart uses

| Challenge | Chart | Data |
|---|---|---|
| CC1 | Davies: world Gini map with year slider; US incomes by percentile | his repository (raw links) |
| CC2 | Top 1% pre-tax income share, US, UK, France | WID via the Our World in Data chart API, notebook download |
| CC2 | UK marginal rate on the next £1, stacked by component, peaks labelled | Economics Observatory raw CSV; cumulative rates turned into layers in the spec |
| CC3 | Effective tax rate by wealth group, US 2018–20 | Balkir, Saez, Yagan and Zucman (2025), Table 2 |
| CC3 | Top 400 vs full population, two estimates | same, and Splinter (2025) as reported by Cato and the Tax Foundation |
| CC5 | Richest 10%'s income share, six countries, live | World Bank Indicators API (`"property": "[1]"`) |
| CC5 | Top income tax rate vs VAT, coloured by wealth tax | Wikipedia table, scraped and tidied in the notebook |
| CC6 | Six indicators for 22 strategic authorities; GM highlighted, London dashed, 2017 marked | course week-7 data, downloaded by a Python loop, embedded by a JavaScript loop |
| CC7 | Scotland: points at council coordinates, extra income tax on local pay (2024–25 bands) | course pay data and map file; own tax calculation (notebook) |
| CC7 | Greater Manchester: deprivation decile by neighbourhood, council names, grey base layer and "No data" tooltip | IoD 2025 via course files; map-data boundaries |
| CC8 | Two charts from the class prices data (to add) | AutoCPI, via the class notebooks |
| CC9 | Scotland vs rest of UK marginal income tax: tax-year menu (2024–25 to 2026–27) and income slider with a live readout | gov.scot and gov.uk bands; computed inside the chart |
| CC9 | Strategic authority explorer: menus for indicator and authority, median authority dashed | `data/cc9_strategic_authorities.csv`, written by the CC6 notebook |

Colour keeps one meaning across charts: red marks the focus (the US, the top 400, Greater Manchester, an active wealth tax,
the allowance taper), blue the comparison.

## Testing

| Item | How it was checked |
|---|---|
| 10 specs | Compiled with Vega-Lite 6.5.0, run in Vega 6.4.0 (headless), no warnings; rendered at 680 px and 300 px wide and inspected |
| Pages | Scripts run with mocked browser functions: all targets exist, all local files resolve, placeholders stay until data exist, the dashboard loop embeds six charts and switches between raw and local links. Static full-page previews at desktop and phone width with the real fonts |
| CC6 and CC7 notebooks | Run end to end on the live course files; output identical to the files in `data/` (including the CC9 table) |
| CC9 calculator | Readout computed by Vega for 10 year/income cases, all equal to independent arithmetic to the penny; £50,000 in 2026–27 gives £8,982.05, as in a published worked example |
| CC5 notebook | Run on a fixture with the live table's two-row header and real cell texts from 21 jurisdictions (12 Nov 2026); 30 value checks pass. Not run against live Wikipedia |
| CC2 notebook | Run on a mocked response in the Chart API's documented CSV layout. Not run against the live API |
| CC5 live chart | Tested with a mocked response in the World Bank format; the URL follows the course's working examples. Live call not tested |
| Not tested | A real browser; the CC1 found charts' data links on publication day (the Gini map reads a former student's repository) |
