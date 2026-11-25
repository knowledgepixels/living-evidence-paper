#!/usr/bin/env python3
"""Pull a snapshot of the published Project Delphi material into analysis/data/.

Two sources are read, both public and without authentication:

  1. The nanopublication network, through the Nanopub Query SPARQL endpoint
     (https://query.knowledgepixels.com/repo/full). All nanopublications
     signed by the three Project Delphi publishing keys are listed, with the
     assessments, claims and legacy Bayesian statements they carry.
  2. The Project Delphi application (https://scienceoracle.com), through its
     public read API: corpus totals, per-domain counts, economic forecasts.

The time of the snapshot is recorded in data/snapshot.json. Run analyze.py
afterwards to turn the snapshot into the numbers and tables used in the paper.
"""

import csv
import io
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SPARQL = "https://query.knowledgepixels.com/repo/full"
APP = "https://scienceoracle.com/api"
DATA_DIR = Path(__file__).parent / "data"
USER_AGENT = "living-evidence-paper-analysis/1.0"

# Public key hashes (SHA-256 of the public key) of the keys that sign
# Project Delphi nanopublications.
KEYS = {
    "4d848a970fc7663c3bdc39fc942260cba139e725a9243d0cc51f78dd102fd785": "pipeline-bot-2026-03",
    "f3c0b0bab578b89d76861329e75651f32c7c8287557dd5ddb5a07cbb7118fecb": "author-key-1",
    "403d674304853131343af2fd56c48a808c8754d0a7aa32ffb35aa0960cdbd97b": "author-key-2",
}

PREFIXES = """
prefix npa: <http://purl.org/nanopub/admin/>
prefix npx: <http://purl.org/nanopub/x/>
prefix np: <http://www.nanopub.org/nschema#>
prefix dct: <http://purl.org/dc/terms/>
prefix prov: <http://www.w3.org/ns/prov#>
prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#>
prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
"""

# Restricting ?pubkey with a filter (rather than VALUES up front) lets the
# endpoint start from the signature index, which is much faster.
KEY_FILTER = "filter(?pubkey in (" + ", ".join(f'"{k}"' for k in KEYS) + "))"

# A nanopublication counts as live when no nanopublication signed by the same
# key invalidates it (npx:invalidates covers retractions and supersessions).
LIVE = "filter not exists { ?inv npx:invalidates ?np ; npa:hasValidSignatureForPublicKeyHash ?pubkey }"

# The ontology moved namespace several times (levin-kg, probknow, delphi), so
# predicates are matched by local name.
def local(var, name):
    return f'filter(strends(str({var}), "{name}"))'


QUERIES = {
    # One row per nanopublication signed by one of the keys.
    "nanopubs": f"""{PREFIXES}
select ?np ?created ?pubkey ?live
       (group_concat(distinct str(?type); separator="|") as ?types)
       (sample(?label) as ?label) (sample(?domain) as ?domain)
where {{
  graph npa:graph {{
    ?np npa:hasValidSignatureForPublicKeyHash ?pubkey ; dct:created ?created ;
        np:hasPublicationInfo ?pi .
    optional {{ ?np npx:hasNanopubType ?type }}
    optional {{ ?np rdfs:label ?label }}
    bind(if(exists {{ ?inv npx:invalidates ?np ; npa:hasValidSignatureForPublicKeyHash ?pubkey }}, 0, 1) as ?live)
  }}
  {KEY_FILTER}
  optional {{ graph ?pi {{ ?np ?dp ?domain . {local("?dp", "ontology/domain")} }} }}
}} group by ?np ?created ?pubkey ?live""",

    # One row per assessment that a live nanopublication introduces.
    "assessments": f"""{PREFIXES}
select ?np ?pubkey ?assessment ?class ?assessmentType ?score ?verdict ?probability ?confidence ?agent ?claim
where {{
  graph npa:graph {{
    ?np npa:hasValidSignatureForPublicKeyHash ?pubkey ; np:hasAssertion ?a ; npx:introduces ?assessment .
    {LIVE}
  }}
  {KEY_FILTER}
  graph ?a {{
    ?assessment a ?class . filter(strends(str(?class), "Assessment"))
    optional {{ ?assessment ?tp ?assessmentType . {local("?tp", "ontology/assessmentType")} }}
    optional {{ ?assessment ?sp ?score . {local("?sp", "ontology/hasScore")} }}
    optional {{ ?assessment ?vp ?verdict . {local("?vp", "ontology/hasVerdict")} }}
    optional {{ ?assessment ?pp ?probability . {local("?pp", "ontology/hasProbability")} }}
    optional {{ ?assessment ?cp ?confidence . {local("?cp", "ontology/hasConfidence")} }}
    optional {{ ?assessment prov:wasAttributedTo ?agent1 }}
    optional {{ ?assessment ?ap ?agent2 . {local("?ap", "ontology/assessedBy")} }}
    bind(coalesce(?agent1, ?agent2) as ?agent)
    optional {{ ?claim ?hp ?assessment . {local("?hp", "ontology/hasAssessment")} }}
  }}
}}""",

    # Mean score per rubric dimension and assessing agent (dimension scores are
    # parts of an introduced assessment, so they are aggregated on the server).
    # Only the current namespace has dimension parts.
    "dimension_scores": f"""{PREFIXES}
prefix delphi: <https://w3id.org/delphi/ontology/>
select ?assessmentType ?agent (count(?part) as ?n) (avg(?score) as ?mean)
where {{
  graph npa:graph {{
    ?np npa:hasValidSignatureForPublicKeyHash ?pubkey ; np:hasAssertion ?a ; npx:introduces ?whole .
    {LIVE}
  }}
  {KEY_FILTER}
  graph ?a {{
    ?whole prov:wasAttributedTo ?agent .
    ?part dct:isPartOf ?whole ; delphi:assessmentType ?assessmentType ; delphi:hasScore ?score .
  }}
}} group by ?assessmentType ?agent""",

    # One row per claim that a live nanopublication introduces.
    "claims": f"""{PREFIXES}
select ?np ?pubkey ?claim ?kind
where {{
  graph npa:graph {{
    ?np npa:hasValidSignatureForPublicKeyHash ?pubkey ; np:hasAssertion ?a ; npx:introduces ?claim .
    {LIVE}
  }}
  {KEY_FILTER}
  graph ?a {{
    ?claim a ?class . filter(strends(str(?class), "/Claim"))
    optional {{ ?claim dct:type ?kind }}
  }}
}}""",

    # Every statement of the March-June 2026 pipeline key, which published one
    # statement per nanopublication.
    "legacy_statements": f"""{PREFIXES}
select ?np ?created ?s ?p ?o
where {{
  graph npa:graph {{
    ?np npa:hasValidSignatureForPublicKeyHash "4d848a970fc7663c3bdc39fc942260cba139e725a9243d0cc51f78dd102fd785" ;
        dct:created ?created ; np:hasAssertion ?a .
  }}
  graph ?a {{ ?s ?p ?o }}
}}""",

    # Revisions recorded on evidence items (executed tests).
    "evidence_revisions": f"""{PREFIXES}
select ?np ?evidence ?claim ?revision ?started
where {{
  graph npa:graph {{
    ?np npa:hasValidSignatureForPublicKeyHash ?pubkey ; np:hasAssertion ?a ; npx:introduces ?evidence .
    {LIVE}
  }}
  {KEY_FILTER}
  graph ?a {{
    ?evidence a ?class . filter(strends(str(?class), "/EvidenceItem"))
    optional {{ ?claim ?hp ?evidence . {local("?hp", "ontology/hasEvidence")} }}
    optional {{ ?evidence prov:qualifiedRevision ?revision . optional {{ ?revision prov:startedAtTime ?started }} }}
  }}
}}""",
}


def http_get(url, accept, timeout=300):
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def sparql_csv(query):
    url = SPARQL + "?" + urllib.parse.urlencode({"query": query})
    return http_get(url, "text/csv").decode("utf-8")


def fetch_network():
    counts = {}
    for name, query in QUERIES.items():
        print(f"query {name} ...", flush=True)
        text = sparql_csv(query)
        rows = list(csv.reader(io.StringIO(text)))
        # Sort the rows so that two snapshots of the same state are identical.
        header, body = rows[0], sorted(rows[1:])
        with open(DATA_DIR / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(body)
        counts[name] = len(body)
        print(f"  {len(body)} rows")
    return counts


def fetch_app():
    print("app stats ...", flush=True)
    stats = json.loads(http_get(f"{APP}/stats", "application/json"))

    print("app domains ...", flush=True)
    domains = json.loads(http_get(f"{APP}/delphi/domains", "application/json"))
    with open(DATA_DIR / "app_domains.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["domain", "papers", "claims", "hypotheses"])
        for d in sorted(domains["domains"], key=lambda d: d["domain"]):
            w.writerow([d["domain"], d["papers"], d["claims"], d["hypotheses"]])

    # The forecast list is about 20 MB; only its aggregates are kept.
    print("app economic forecasts ...", flush=True)
    forecasts = json.loads(http_get(f"{APP}/economic-hypotheses", "application/json", timeout=600))
    sized = [x for x in forecasts if x.get("marketSizeB")]
    years = [x["yearsToAchievement"] for x in sized if x.get("yearsToAchievement") is not None]
    sources = {}
    for x in forecasts:
        name = x.get("sourceName") or ""
        key = "scout agents" if name.endswith(" scout") else name
        sources[key] = sources.get(key, 0) + 1
    economic = {
        "forecasts": len(forecasts),
        "forecasts_with_market_size": len(sized),
        "market_size_sum_billion_usd": round(sum(x["marketSizeB"] for x in sized), 1),
        "market_size_max_billion_usd": max(x["marketSizeB"] for x in sized),
        "mean_years_to_achievement": round(sum(years) / len(years), 2),
        "by_source": dict(sorted(sources.items(), key=lambda kv: -kv[1])),
    }

    print("app timeline ...", flush=True)
    timeline = json.loads(http_get(f"{APP}/timeline", "application/json"))
    years_covered = [t["year"] for t in timeline if t.get("nodeCount")]

    app = {
        "stats": stats,
        "domains_scope": domains.get("scope"),
        "domains_generated_at": domains.get("generatedAt"),
        "domain_count": len(domains["domains"]),
        "economic": economic,
        "publication_years": [min(years_covered), max(years_covered)],
    }
    with open(DATA_DIR / "app.json", "w", encoding="utf-8") as f:
        json.dump(app, f, indent=2)
        f.write("\n")
    return app


def main():
    DATA_DIR.mkdir(exist_ok=True)
    taken = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    counts = fetch_network()
    fetch_app()
    snapshot = {
        "taken_at": taken,
        "sparql_endpoint": SPARQL,
        "app_api": APP,
        "keys": KEYS,
        "rows": counts,
    }
    with open(DATA_DIR / "snapshot.json", "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)
        f.write("\n")
    print("snapshot taken at", taken)


if __name__ == "__main__":
    main()
