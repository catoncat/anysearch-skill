# AnySearch Domain Catalog

Captured 2026-07-07. Call `get_sub_domains` live for the latest schema.

## finance (6 sub_domains)

### finance.quote
Real-time and historical quotes: stocks, forex, crypto, commodities, indices, ETFs, futures.
- `type` (required): `stock` | `forex` | `crypto` | `commodity` | `index` | `etf`
- `symbol` (required): International ticker. stock: `AAPL`; forex: `EURUSD`; crypto: `BTCUSD`; commodity: `CLUSD`
- `cn_code` (required): Chinese market symbol. stock: `600519.SH`; index: `399300.SZ`; etf: `510300.SH`; forex: `USDCNH.FXCM`
- `period`: `7d`|`14d`|`30d`|`90d`|`180d`|`1y`|`5y` or `{N}d`. Intl default `7d`, CN default `30d`

### finance.news
Global financial news, company announcements, broker research.
- `type` (required): `general` | `stock` | `flash` (Chinese headlines) | `announcement` (A-share)
- `symbol`: Intl ticker, for type=stock
- `cn_code`: A-share ticker, for type=announcement
- `news_src`: For type=flash. `sina`|`wallstreetcn`|`10jqka`|`eastmoney`|`cls`|`yicai`|`yuncaijing`|`fenghuang`|`jinrongjie`
- `period`: Time range. flash/announcement default `1d`

### finance.fundamental
Financial statements, valuation, analyst ratings, shareholders, SEC filings.
- `type` (required): `overview` | `income` | `balance` | `cashflow` | `indicator` | `holder`
- `symbol` (required): Intl ticker, for type=overview
- `cn_code` (required): A-share ticker, for type=income/balance/cashflow/indicator/holder
- `period`: For type=holder, default `1y`

### finance.screen
Screen stocks by sector, country (international only).
- `type` (required): `stock` | `etf`
- `sector`: GICS sector. `Technology`|`Healthcare`|`Financial Services`|`Consumer Cyclical`|`Consumer Defensive`|`Industrials`|`Energy`|`Basic Materials`|`Communication Services`|`Real Estate`|`Utilities`
- `country`: ISO 3166-1 alpha-2. `US`|`JP`|`GB`|`DE`|`CN`|`HK`

### finance.calendar
Earnings, dividends, IPO, economic data release schedules.
- `type` (required): `earnings` | `dividends` | `ipos` | `economic`
- `period`: Forward-looking range, default `7d`
- `symbol`: For type=dividends

### finance.macro
Macroeconomic indicators: GDP, CPI, PMI, interest rates, money supply.
- `type` (required): `gdp` | `cpi` | `fed_funds` | `treasury` | `unemployment` | `nonfarm` | `shibor` | `lpr` | `money_supply` | `social_finance`
- `period`: Varies by type. gdp `2y`, cpi/lpr `1y`, shibor `30d`

## academic (5 sub_domains)

### academic.search
Cross-discipline paper search by keyword, title, author, institution.
- `category`: Subject, comma-separated. `Computer Science`|`Medicine`|`Biology`|`Chemistry`|`Physics`|`Mathematics`|`Materials Science`|`Engineering`|`Environmental Science`|`Geology`|`Geography`|`Sociology`|`Psychology`|`Economics`|`Business`|`Political Science`|`Linguistics`|`Philosophy`|`History`|`Art`|`Education`|`Law`
- `min_citations`: Min citation count, e.g. `100`
- `open_access`: `true`|`false`
- `sort`: `cited_by_count`|`publication_date`|`publication_year`|`relevance_score`|`display_name`, append `:asc`/`:desc`
- `venue`: Journal/conference, e.g. `NeurIPS`|`ICML`|`Nature`
- `year_from` / `year_to`: 4-digit year
- `doi`: Direct DOI lookup, skips keyword search
- `type`: Doc type filter. `article`|`book`|`book-chapter`|`dataset`|`dissertation`|`preprint`|`report`|`review`

### academic.citation
Citation relationships, counts, reference lists by DOI or title.
- `id` (required): Persistent identifier (DOI/PMID/ISSN/ISBN/ORCID/OMID/OCI). No type prefix.
- `op`: `metadata`(default) | `citations` | `references` | `citation-count` | `reference-count` | `author` | `editor` | `venue-citation-count` | `citation`
- `id_type`: `doi`|`pmid`|`issn`|`isbn`|`orcid`|`omid`. Auto-detected if empty.
- `filter`: RAMOSE filter, e.g. `creation:2020-*-*`
- `sort`: RAMOSE sort, e.g. `creation:desc`
- `year_from` / `year_to`: `YYYY`|`YYYY-MM`|`YYYY-MM-DD`
- `min_citations`: Min citation count
- `open_access`: `true`|`false`
- `venue`: Journal/conference name
- `category`: Subject category

### academic.biomedical
MEDLINE journals with MeSH terms and PMC full-text links.
- `source`: `MED`(PubMed) | `PMC` | `PPR`(preprints) | `AGR` | `PAT`
- `sort`: `relevance`(default) | `date` | `pub_date` | `author` | `journal` | `cited`
- `field`: `tiab`(title+abstract, default) | `title` | `author` | `journal` | `mesh` | `all`
- `year_from` / `year_to`: `YYYY` or `YYYY/MM/DD`
- `date_type`: `pdat`(default) | `edat` | `mdat`
- `open_access`: `true`|`false`
- `has_pdf`: `true`|`false`

### academic.preprint
Preprint search across CS, physics, math, biology, economics.
- `sort`: `relevance`(default) | `date_submitted` | `date_updated`
- `order`: `asc` | `desc`(default)
- `field`: `ti`|`au`|`abs`|`co`|`jr`|`cat`|`all`(default)
- `year_from` / `year_to`: 4-digit year
- `language`: ISO code, e.g. `en`|`zh`|`de`
- `doi`: Direct DOI lookup
- `open_access`: `true`|`false`

### academic.dataset
Research datasets across Zenodo, Dryad, Figshare.
- `client_id`: Repository, e.g. `cern.zenodo`|`figshare.ars`|`bl.dryad`
- `resource_type`: `Dataset`|`Software`|`Text`|`Image`|`Audiovisual`|`Collection`
- `year_from` / `year_to`: 4-digit year

## code (2 sub_domains)

### code.snippet
Search real code across 1M+ GitHub repositories.
- `lang`: Programming language, e.g. `TypeScript`|`Python`
- `path`: File path pattern, e.g. `src/components/`
- `repo`: GitHub repo, e.g. `facebook/react`

### code.doc
Developer documentation by library name across npm, PyPI, Cargo.
- `library` (required): Library/framework name, e.g. `react`|`express`

## health (3 sub_domains)

### health.drug
Drug labels, adverse reactions, interactions, recalls.
- `type` (required): `name` (drug name search) | `ndc` (NDC code) | `upc` (UPC barcode)

### health.trial
Clinical trial registry by disease, drug, phase, region.

### health.stats
Global public health stats across 194 countries: mortality, morbidity, life expectancy, disease burden.

## legal (3 sub_domains)

### legal.statute
Legal text lookup for laws, regulations, regulatory rules.
- `collection`: `FR`|`CFR`|`USCODE`|`BILLS`|`PLAW`|`USCOURTS`|`CREC`|`STATUTE`
- `title`: CFR Title number, e.g. `40`(EPA)|`21`(FDA)|`49`(Transportation)
- `agency`: Publishing agency slug, e.g. `environmental-protection-agency`|`securities-and-exchange-commission`
- `doc_type`: `RULE`|`PRORULE`|`NOTICE`|`PRESDOCU` (Federal Register); or `REG`|`DIR`|`DEC` (EUR-Lex); or `ukpga`|`uksi` (UK)
- `date_from` / `date_to`: `YYYY-MM-DD`
- `historical`: `true`|`false`
- `language`: ISO 639-1, e.g. `en`|`fr`|`de`

### legal.legislation
US Congress bill status, voting records, committee deliberations.
- `congress`: Congress session number, e.g. `119` for 2025-2026

### legal.case
Court decisions and opinions across CN, US, CA, ECHR.
- `doc_type`: `o`(opinions) | `r`(RECAP) | `rd`(RECAP docs) | `d`(dockets) | `p`(people) | `oa`(oral args); or ECHR: `JUDGMENTS`|`DECISIONS`|`COMMUNICATEDCASES`
- `database_id`: Court code, e.g. `csc-scc`(SCC)|`onca`(ONCA)|`bcca`(BC CA)
- `case_id`: CanLII case ID, e.g. `2008scc9`
- `respondent`: ISO 3166-1 alpha-3 country, e.g. `TUR`|`FRA`
- `language`: `en`(default)|`fr`

## security (4 sub_domains)

### security.intel
Threat intelligence for IP, domain, URL, file hash.
- `ioc` (required): Indicator of compromise — domain, IP, URL, or file hash

### security.vuln
CVE vulnerability details, CVSS, affected versions, patches.
- `type` (required): `cve` | `commit` | `package`
- `value` (required): CVE ID / 40-char hex / `ecosystem:name@version`. Comma-separated for batch.

### security.scan
Submit file hash, URL, IP, domain to 70+ vendor aggregate scan.
- `ioc` (required): Domain, IP, URL, or file hash (MD5/SHA1/SHA256)

### security.noise
Check if IPv4 is internet background scanning noise or known legitimate service.
- `ip` (required): Single IPv4 address, e.g. `8.8.8.8`

## business (4 sub_domains)

### business.company
Company registration, shareholders, executives, business status.
- `type`: `ChineseEnterprise`|`GlobalLEI`|`USFilings`
- `keyword`: Company name / credit code / LEI code / ticker

### business.trade
International trade statistics by commodity code, country, period.
- `type`: `GlobalBilateralTrade`|`USImportExport`
- `hs_code`: 2/4/6/10 digits
- `flow`: `export`|`import`|`both`
- `location`: Partner country
- `date_start`: Year, e.g. `2023`

### business.jobs
Global job listings across 16+ countries.
- `type`: `GeneralJobs`|`RemoteJobs`|`USFederalJobs`
- `keyword`: Search keyword
- `location`: City/region/country
- `salary_min`: Min annual salary USD

### business.people
Business contacts by title, company, location.
- `type`: `PeopleSearch`|`EmailLookup`
- `keyword`: Search keyword / company domain
- `title`: e.g. `CTO`|`Head of Engineering`
- `seniority`: `executive`|`senior`|`entry`
- `location`: e.g. `California`|`London`

## ip (1 sub_domain)

### ip.global
Global patent aggregation via EPO DOCDB/INPADOC, 100+ countries.
- `type`: `GlobalPatent`
- `keyword`: Search keyword
- `applicant`: Applicant/organization name
- `ipc`: IPC/CPC classification, e.g. `H01L`|`G06N`
- `date_start`: Year or YYYYMMDD

## energy (2 sub_domains)

### energy.electricity
Electricity market data: prices, generation, demand, carbon intensity.
- `type`: `EUElectricity`|`AustralianElectricity`|`USEnergyData`|`GlobalElectricity`
- `location`: Region name
- `metric`: `price`|`generation`|`emissions`|`demand`|`capacity`
- `date_start` / `date_end`: `YYYY-MM-DD` or `YYYY`

### energy.production
Energy production/consumption for oil, gas, coal, nuclear, renewables.
- `type`: `USEnergyData`
- `keyword`: e.g. `crude oil production`
- `frequency`: `monthly`|`annual`|`quarterly`
- `location`: Region
- `date_start`: `YYYY-MM` or `YYYY`

## environment (1 sub_domain)

### environment.aqi
Real-time global air quality index and PM2.5/PM10.
- `type`: `GlobalAirQuality`
- `location`: Zip code / coordinates / city name, e.g. `20002`|`38.9,-77.0`|`Beijing`

## agriculture (1 sub_domain)

### agriculture.fao
FAO global agriculture statistics: production, trade, food prices.
- `type`: `GlobalAgriculture`
- `domain`: `production`|`trade`|`prices`
- `keyword`: e.g. `wheat production`|`rice trade`
- `location`: `World`|`China`
- `date_start`: Year

## travel (2 sub_domains)

### travel.flight_status
Real-time flight departure/arrival status, gate info, delays.
- `type`: `FlightStatus`
- `date` (required): `YYYY-MM-DD`
- `departure` (required): IATA 3-letter code, e.g. `PEK`|`LAX`
- `arrival` (required): IATA 3-letter code
- `flight_number`: e.g. `DL47`|`CA981`

### travel.flight
Search global flight tickets by origin, destination, date, cabin class.
- `type`: `FlightSearch`
- `date` (required): Departure date, `YYYY-MM-DD` or `DD/MM/YYYY`
- `departure` (required): IATA 3-letter code
- `arrival` (required): IATA 3-letter code
- `origin` / `destination`: IATA code or city name (alternative to departure/arrival)
- `cabin_class`: `Economy`|`Business`|`First`|`PremiumEconomy`
- `adults` / `children` / `infants`: Counts
- `currency`: e.g. `USD`|`CNY`
- `return_date`: `DD/MM/YYYY`, empty = one-way

## film (1 sub_domain)

### film.torrent
Search film and music BT torrent resources with magnet links, file size, seeder count.

## gaming (2 sub_domains)

### gaming.esports
Esports stats for League of Legends and other Riot titles.
- `type` (required): `player`|`ranked`|`mastery`|`live_game`|`match_detail`|`leaderboard`|`champion`|`item`|`champion_rotation`
- `region`: Riot server region. `kr`|`na`|`euw`|`eune`|`jp`|`br`|`la1`|`la2`|`oc`|`tr`|`ru`|`sg`
- `game_name`: Riot ID, e.g. `Faker#KR1` or `Tyler1`
- `match_id`: Fully-qualified match ID, e.g. `KR_7482819248`
- `queue`: `RANKED_SOLO_5x5`|`RANKED_FLEX_SR`
- `tier`: `CHALLENGER`|`GRANDMASTER`|`MASTER`|`DIAMOND`|`EMERALD`|`PLATINUM`|`GOLD`|`SILVER`|`BRONZE`|`IRON`
- `division`: `I`|`II`|`III`|`IV`
- `champion`: Champion name substring for mastery filter

### gaming.store
Steam game prices, discounts, ratings, online player count, achievements.

## social_media (1 sub_domain)

### social_media.social_media
Social media search and retrieval across platforms.
- `type`: `weibo`|`weibo_hot`|`zhihu`|`zhihu_hot`|`x_top`|`x_latest`|`x_media`|`x_people`|`x_lists`|`reddit_post`|`reddit_community`|`reddit_comment`|`reddit_media`|`reddit_people`|`linkedin_people`|`linkedin_jobs`|`linkedin_company`|`linkedin_posts`|`sogou_wechatmp`
- `keyword`: Search keywords
- `region`: For weibo_hot only, e.g. `Beijing`|`Shanghai`

## resource (1 sub_domain)

### resource.image
Professional photography, stock photos, SVG, illustrations, vector graphics.