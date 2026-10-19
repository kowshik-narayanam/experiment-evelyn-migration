# Enrichment in NSS — What It Actually Is, and Why It Sells

> Sales-oriented notes. Written to be *said out loud* in a discovery call or a technical
> deep-dive, not recited from a datasheet. Everything technical here is verified against the
> code (branch: `master`, BP `v3.10.0-dev`). Where the market framing outruns what our code
> literally does, it's flagged — don't overclaim in front of a compliance buyer.

---

## The one-sentence version

**Enrichment is where NSS cleans up and *upgrades the data* before the matching engine ever
looks at it — so the auto-decision (clear vs. escalate) is more accurate.** It is our answer to
the oldest problem in screening: *garbage , garbage out.*

There are two enrichers, and they map to the two fields that decide most alerts:

| What we call it | What it really does | The field it sharpens |
|---|---|---|
| **Name enrichment** ("Ticker Lookup") | Turns an un-screenable securities/derivatives string (`AAPL 15JAN 150 CALL`) into the real **issuer name** (`Apple Inc.`) | the **name** match |
| **Location enrichment** ("Address Lookup") | Turns a messy free-text address (`"NYC"`, `"Houston"`) into a **canonical, geo-coded** location (country/state/city + latitude/longitude) | the **address** match |

Neither one makes a decision. Both exist to feed the decision engine cleaner inputs.

---

## The mental model (lead with this)

Screening runs in three beats:

```
1. PULL   the customer record + its watchlist hits (WLEs) from the screening system
2. ENRICH the name and address data on BOTH sides            ← this doc
3. SCORE  each hit with the deterministic model → clear (false positive) or escalate (needs review)
```

Enrichment sits **strictly between the watchlist pull and the model.** That single fact is the
whole sales story, and it's structurally guaranteed in the business process (verified in the BP
flow: `WLEs Found → Data Enrichment → Names Classification Model → report`).

Three properties fall out of that position, and each is a selling point:

- **Accuracy with zero audit cost.** Enrichment *adds data fields only.* The deterministic rule
  engine still makes and traces every clear/escalate decision. So you improve outcomes **without
  changing your auditable decision logic** — nothing for model risk / validation to re-approve.
- **Fail-open and pay-for-value.** Each enricher is **off by default** and turned on per tenant
  with a wizard toggle. On a *no-hit* alert the entire enrich+score stage is skipped. If a
  geocode returns nothing or errors, screening **silently falls back to the original data** — it
  can only add signal, never drop a record. You spend compute only where it can flip an outcome.
- **It's the data layer, not another algorithm.** See the next section for why that's the point.

---

## Why a buyer should care (the pain enrichment actually addresses)

Sanctions screening's dirty secret: **false positives are a data problem, not an algorithm
problem** (Finextra; ComplyStream). The engine is asked to match *dirty, unstructured* customer
data against *structured* watchlist entries — and no amount of algorithm tuning fixes bad inputs.
The industry-repeated proof point is the **threshold trap**: tighten matching to cut false
positives and you *also* cut true-positive detection; loosen it and real hits drown in noise.
You cannot tune your way out. You have to fix the data. **That is what enrichment does.**

The commercial weight behind that:

- **90–95%+ of sanctions alerts are false positives** (PwC and widely-cited industry
  benchmarks; some sanctions models quoted at 99%+). *Directional figures — present as "industry
  benchmarks," not a WorkFusion measurement.*
- Review cost commonly framed at **~$15–25 per alert** (analyst time). A mid-tier bank running
  tens of thousands of alerts a month is burning a recurring headcount budget on dead ends.
- **Alert fatigue is a compliance risk, not just a cost.** Exhausted teams grinding a noisy
  queue are the ones who miss the genuine hit — the failure mode that draws enforcement.
- LexisNexis reports that **structured entity + address data enables false-positive reductions of
  up to ~75%with a materially smaller review queue. Enrichment is exactly that "structure the
  data first" move.

**The line:** *"You've probably tuned your matching rules as far as they'll go. The next gain
isn't in the algorithm — it's in the data going into it. That's what our enrichment layer is."*

---

## The problem, in one picture

A trading desk does not send you clean names. It sends **instruments**:

```
AAPL 15JAN 150 CALL
COM 27 Jan23 15.5 Weekly Call
[COM24JUL18_1234AB.CD4] Com Corp [COM] Jul 24 1234 Put (EU)
```

A sanctions/PEP watchlist contains **issuer and person names** — *Apple Inc.*, *Gazprom PJSC*, a
designated individual. Point a name-matcher at the raw option string and you get garbage: the
string contains **no issuer name to match**, so you get either misses (a sanctioned issuer sails
through un-alerted) or spurious partial-token noise. Legacy name-tuned screening tools **cannot
screen a trading book at all** without a resolution step first. This is a *capability gap*, not
an efficiency one.

## What NSS does

Ticker Lookup recognizes that the leading token (or a bracketed symbol) of that instrument string
is a **stock ticker**, looks it up against a company dataset, and attaches the resolved **issuer
name** to the record. Downstream, the model screens *"Apple Inc."* against your watchlist instead
of *"AAPL 15JAN 150 CALL."*

- The resolved name is stored as a **derived** name with `source = tickersDS`; the **original
  instrument string is preserved** for display and audit.
- Every enrichment carries a plain-English audit line:
  *"The screened name `AAPL 15JAN 150 CALL` was enriched by ticker information to `Apple Inc.`"*
- Whenever a name or alias was enriched, the alert is **flagged (`tickerUsed`)** — so you get
  analytics on how often securities enrichment is doing real work in your pipeline.

## The reference data maintains itself

The ticker→company map is **not a spreadsheet your team owns.** A separate, scheduled process
downloads the **SEC's authoritative `company_tickers.json`**, diffs it against the current
dataset, updates it, and can **email compliance the exact list of tickers added and issuers
renamed.** Two things to stress:

- **Zero maintenance burden** — you're not paying an analyst to hand-curate a securities table.
- **It's out-of-band.** The refresh runs on a maintenance schedule in its own business process;
  it adds **zero latency** to live screening, which only reads the already-loaded table.

## Why it sells

- *"Your traders' positions arrive as `AAPL 15JAN 150 CALL`, not `Apple Inc.` We recognize the
  ticker, resolve the real issuer, and screen **that** — so a sanctioned issuer can't hide behind
  option jargon."*
- *"It's the difference between clearing a ticker-collision false positive and escalating a
  genuine hit — because the engine is finally comparing a real name to a real name."*
- *"The mapping self-refreshes from the SEC feed and can email your team every change — audit
  evidence, delivered, with no data-ops project."*
- *"Surgical by config: enrich only Securities-typed records (default) or everything; enrich
  aliases too or just the primary name for speed. Wizard toggles, no redeploy."*
- *"Built-in guardrails: FX currency codes (USD, EUR, JPY…) are never mistaken for tickers, and
  Bloomberg-style bracketed strings still resolve using the issuer name embedded in the string
  even when the symbol isn't in the dataset."*

## The regulatory hook (frame the urgency)

Securities screening is now a distinct enforcement expectation, not a nice-to-have. **OFAC settled ~$11.8M** with a large US retail brokerage in the first public action with a
significant **securities** component — trades in **CMIC**-program securities, plus sectoral /
blocked-bank exposure. The industry takeaway everyone repeated: **"screen securities, not just
customers."** Sectoral programs (SSI under E.O. 13662, CMIC) and the **OFAC 50% Rule** mean
exposure can hide behind an instrument whose ticker and issuer appear on *no* list.

**Position honestly:** ticker enrichment is the **essential first link** — it turns an
un-screenable instrument string into a screenable issuer name, without which none of the rest is
even possible. The deeper discipline (ownership-tree / beneficial-owner resolution, issuance-date
and maturity metadata for sectoral scoping) is where the *market* is heading; don't claim NSS
performs full ownership-graph resolution today. Sell the foundation we own: **"You can't screen
what you can't name. We make the instrument nameable."**

## Honest scope (so you don't get caught)

- Resolution is **ticker-symbol based against SEC US-listed companies** (`company_tickers.json`).
  It is **not** arbitrary ISIN/CUSIP/SEDOL resolution or a global issuer master.
- It recognizes **specific instrument string formats** — space-delimited option strings
  (`SYMBOL date strike call/put`) and Bloomberg-style bracketed option strings. Symbols are 1–4
  letters. A format outside those patterns is passed through unchanged (no harm, no enrichment).

---

## The problem, in one picture

Address is one of the **highest-value discriminators** an analyst uses to clear or confirm a name
hit — a name alone rarely settles anything; DOB, nationality, and **address** do. But addresses
arrive dirty on **both** sides of the comparison:

- The customer record says **`"NYC"`**; the watchlist says **`"New York"`.** A string matcher
  sees a **mismatch** — and adds noise instead of signal.
- A watchlist hit says **`"Houston"`** with no country or state. There's nothing structured to
  compare — the address field is simply **wasted**.

Free-text, partial, and transliterated addresses break screening **both ways**: they manufacture
false positives (a free-text blob collides with a listed city/country) *and* they hide true
matches (the real hit never normalizes to a comparable form). *"False positives are a data
problem"* — and address is the messiest data in the file.

## What NSS does

Location enrichment sends free-text addresses to a **geocoding provider** and gets back a clean,
**structured, standardized** location — country, state, city, street, a canonical formatted
address, **plus latitude/longitude** — and attaches it to the record (`enriched[]`,
`source = provider`). Verified end-to-end:

```
"New York"  →  United States / NY / New York / "New York, NY, USA"  (40.7127753, -74.0059728)
"Houston"   →  United States / TX / Houston  / "Houston, TX, USA"   (29.7600771, -95.3701108)
```

Key behaviors, each with a sales angle:

- **It repairs both sides.** Independently toggle enrichment of your **input** records and of the
  **watchlist hits** (`settings.input` / `settings.wle`) — because address quality is usually
  poor on both.
- **It's precisely scoped.** Only **free-text blobs** get geocoded (an address string present,
  but country/state/city/street all empty). Records you already receive fully structured are left
  untouched — **you don't pay to re-geocode clean data.**
- **It's fail-open.** Empty or errored geocode → the model transparently falls back to the
  original address. Turning it on **cannot break screening.**

## The capability plain screening can't have: geo-distance

Once both sides carry coordinates, comparison can move from brittle string overlap to **real-world
distance.** With proximity matching on, the model computes the great-circle (Haversine) distance
between the customer's address and the hit's address:

- **8 km apart → strong match.** **900 km apart → mismatch.** A *physical* proximity judgment, not
  a spelling coincidence.

**Frame it accurately:** proximity matching is a **configurable option, off by default**
(default threshold 50 km, km or mi), and needs enriched coordinates on both sides. Position it as
the **logical extension of geocoding** — "once the data is geocoded, you *can* screen
distance" — not as a claimed industry-standard benchmark.

## Why it sells

- *"Your analysts burn time because a customer's `NYC` doesn't string-match a watchlist's `New
  York`. We geocode both to the same canonical address plus coordinates — so the address field
  either genuinely clears the alert or genuinely confirms it, instead of adding noise."*
- *"It adds a discriminator plain screening can't have: **distance**. Two addresses 8 km apart
  read as a match; 900 km apart as a mismatch — a physical check, not a spelling one."*
- *"It repairs bad data on **both** sides — your records and the vendor's list — because address
  quality is usually poor on both."*
- *"Zero-risk to switch : no geocode, no problem — screening falls back to the original
  address. It can only add signal, never drop a record."*
- *"Precisely scoped — only free-text addresses get geocoded; data you already receive structured
  is left alone."*

## Honest scope (so you don't get caught)

- The geocoding provider is **Google** — Google Geocoder or Google Places — with a
  **bring-your-own API key.** The actual provider call lives in a WorkFusion platform worker
  (`address-lookup`), not in the screening code.
- **Do not sell an "internal WorkFusion proxy" routing option.** The config exposes a
  `connection_type` field whose *only* selectable value is **`direct`**; "internal proxy" appears
  in a tooltip, not as a usable choice. (Verified — this was the one claim the fact-check flagged.)
- Proximity/geo-distance is **off by default** and requires enriched coordinates on both sides;
  with proximity off, enrichment still helps via the canonical hierarchical fields
  (country → state → city → street).

---

## Config cheat-sheet (what each knob buys)

**Name enrichment (`enrichment.name.*`)**

| Knob | Default | What it buys |
|---|---|---|
| `ticker_lookup` | on | Master on/off for per-alert ticker enrichment |
| `ticker_lookup_enrich_only_securities` | on | On = only Securities-typed records; Off = every record |
| `ticker_lookup_aliases` | on | Also enrich aliases; off = primary name only (a **speed** option) |
| `ticker_lookup_email_notification` | off | Email compliance on each SEC-dataset refresh (added/renamed issuers) |
| `ticker_lookup_notification_addresses` | — | Who gets those emails |

**Location enrichment (`enrichment.location.*`)**

| Knob | Default | What it buys |
|---|---|---|
| `provider` | *(empty = off)* | `GOOGLE` or `GOOGLE_PLACES_API`; empty disables the whole feature |
| `apiKey` | — | Your Google API key |
| `settings.input` | — | Enrich your customer/input addresses |
| `settings.wle` | — | Enrich the watchlist-hit addresses (independent of input) |
| `model.thresholds.proximity_matching.enable_proximity` | off | Turn on **geo-distance** address matching |
| `model.thresholds.proximity_matching.threshold` / `.metric` | 50 / km | Max distance for a strong match, and the unit |

---

## The 30-second pitch (memorize this)

> *"NSS enrichment is the data layer that sits between the watchlist pull and the decision engine.
> For securities, we turn an un-screenable trade string like `AAPL 15JAN 150 CALL` into the real
> issuer, `Apple Inc.`, so your trading book is actually screenable — with a ticker map that
> self-refreshes from the SEC. For addresses, we geocode messy free-text like `NYC` into a
> canonical location with coordinates, on both your data and the watchlist, so the address field
> clears or confirms alerts instead of adding noise — and we can even match on real-world
> distance. It's off by default, fail-open, and adds only data fields — so you get accuracy gains
> with zero change to your auditable decision logic. False positives are a data problem, not an
> algorithm problem. This is how we fix the data."*

---

## Appendix — for the technical buyer (credible, not line-by-line)

- **Pipeline position (guaranteed by the BP):** `Validate WLE → [WLEs Found] → Data Enrichment
  (ticker → location) → Names Classification Model (prepare-for-ml → AutoML bridge →
  save-model-results) → report`. The empty-hit branch skips enrichment *and* the model.
- **Name enrichment** runs in-process per alert (`ticker-lookup-task`); the **dataset refresh**
  is a separate scheduled BP (`ticker-lookup-download-processor`) that pulls SEC
  `company_tickers.json`, diffs it (Guava `Maps.difference`), and replaces the shared ticker
  datastore.
- **Location enrichment** is a two-step shape around a platform worker: `address-lookup-prepare-
  data-task` (collects the deduped set of free-text addresses) → `address-lookup` worker (the
  external Google call) → `save-address-lookup-data-task` (writes `enriched` back onto **both**
  screened data and WLE list).
- **How enriched data reaches the model:** the model document builder swaps in the derived issuer
  name whenever `source` is set, and emits the enriched location (with lat/long) whenever the
  location was enriched — otherwise it uses the original. The Python `AddressMatcher` reads
  lat/long and, under proximity mode, scores on Haversine distance (`r = 6371 km`).
- **Verification note:** these notes were fact-checked against the code — 29/30 load-bearing
  claims confirmed; the one correction (no usable "internal proxy" for location) is reflected
  above. See also [MODEL_INTEGRATION.md](MODEL_INTEGRATION.md), [MAIN_BP_FLOW.md](MAIN_BP_FLOW.md),
  [NAME_MATCHER.md](NAME_MATCHER.md).
