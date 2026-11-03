# Fixtures

`council-ratios-2026-27.csv` holds the 2026-27 area Band D (MHCLG, Table 9) and the March 2026
average house price (UK House Price Index) for 295 English councils, as tabulated by
Mortgage Introducer on 27 July 2026 ("Council Tax by Town: Full 2026 Rankings vs House Value").
`pct` is Band D as a percentage of the average price, rounded to two decimals. Council codes
were added by matching names to the 2025 local authority districts.

The build compares its own Band D figures and ratios against this table. A mismatch means a
parsing error or a revision in the source, and the check output says which.
