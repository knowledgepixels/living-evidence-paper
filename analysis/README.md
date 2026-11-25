# Paper analysis: snapshot of the published material

Code and data behind the counts in the paper: the deployed graph (Section 3.1,
Table 1), the model panels (Table 2), the state of the network (Section 7,
Tables 3 and 4), and the numbers quoted in the case studies.

## Layout

- `fetch_snapshot.py`: takes the snapshot. It reads two public sources, with no
  authentication:
  - the nanopublication network, through the Nanopub Query SPARQL endpoint
    (`https://query.knowledgepixels.com/repo/full`), for every nanopublication
    signed by one of the three Project Delphi keys;
  - the Project Delphi application (`https://scienceoracle.com/api`), for the
    corpus totals, the per-domain counts and the economic forecasts.
- `analyze.py`: turns the snapshot into numbers. It writes `data/stats.json`
  (everything, machine-readable) and `tables.md` (the same numbers as tables).
- `tables.md`: the generated tables. The tables in `index.html` are copied
  from here by hand.
- `data/`: the snapshot.
  - `snapshot.json`: when the snapshot was taken, the endpoints and the keys.
  - `nanopubs.csv`: one row per nanopublication (creation time, key, whether
    it is live, types, label, domain).
  - `assessments.csv`: one row per assessment that a live nanopublication
    introduces (rubric, score, verdict, agent, assessed claim).
  - `dimension_scores.csv`: mean score per rubric dimension and agent.
  - `claims.csv`: one row per published claim, with its kind.
  - `legacy_statements.csv`: every statement of the March–June 2026 pipeline
    key, which published one statement per nanopublication.
  - `evidence_revisions.csv`: evidence items for executed tests and their
    recorded revisions.
  - `app.json`, `app_domains.csv`: totals, forecast aggregates and per-domain
    counts from the application.
  - `stats.json`: output of `analyze.py`.

## Updating the numbers

```
python3 fetch_snapshot.py    # refresh data/ (about half a minute)
python3 analyze.py           # write data/stats.json and tables.md
```

Then carry the changed numbers from `tables.md` into `index.html` and update
the snapshot date given there. Both scripts use only the Python standard
library (Python 3.9 or later).

## Definitions

- **Live**: a nanopublication is live when no nanopublication signed by the
  same key invalidates it (`npx:invalidates`, which covers retraction and
  supersession).
- **Keys**: the three public-key hashes are listed in `fetch_snapshot.py`.
  Nanopublications that only support the content (templates, queries, views,
  the space definition) are signed by other keys and are not counted.
- **Namespaces**: the ontology moved from `levin-kg` to `probknow` to
  `delphi`. Predicates and classes are matched by local name, so all
  generations are counted together.
- **Resolvable now**: a claim counts as resolvable now when every model that
  scored it on the dataset-resolvability rubric gave that verdict.
- **Domain family** (Table 1): the first word of the application's domain
  label, for example `math` in `math-reaction-diffusion-…`.
