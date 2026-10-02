"""HA Lite: holiday config flow for the lazily loading holidays package (vacanza/holidays PRs #3839 + #3844).

Stock 2026.9.3 calls list_supported_countries() at import, which imports every country module and defeats the lazy
registry. This asks the registry for the country codes instead and reads a country's subdivisions from the one
country it builds. Usage: patch_holiday_config_flow.py <.../components/holiday/config_flow.py>. Fails if an anchor is
missing. Home Assistant is Apache-2.0; the edited file keeps its license."""
import sys

P = sys.argv[1]
s = open(P, encoding="utf-8").read()
for old, new in (
    ("from holidays import PUBLIC, country_holidays, list_supported_countries\n",
     "from holidays import PUBLIC, country_holidays\nfrom holidays.registry import EntityLoader\n"),
    ("SUPPORTED_COUNTRIES = list_supported_countries(include_aliases=False)\n\n\n", "\n"),
    ("    if provinces := SUPPORTED_COUNTRIES[country]:\n"
     "        country_data = country_holidays(country, years=dt_util.utcnow().year)\n",
     "    country_data = country_holidays(country, years=dt_util.utcnow().year)\n"
     "    if provinces := list(country_data.subdivisions):\n"),
    ("                        countries=list(SUPPORTED_COUNTRIES),\n",
     "                        countries=sorted(\n"
     "                            EntityLoader.get_country_codes(include_aliases=False)\n"
     "                        ),\n"),
):
    if s.count(old) != 1:
        sys.exit(f"holiday config_flow: anchor not found (or repeated): {old[:60]!r}")
    s = s.replace(old, new)
if "SUPPORTED_COUNTRIES" in s:
    sys.exit("holiday config_flow: SUPPORTED_COUNTRIES still referenced")
open(P, "w", encoding="utf-8").write(s)
print("holiday config_flow patched")
