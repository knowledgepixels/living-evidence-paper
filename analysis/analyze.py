#!/usr/bin/env python3
"""Turn the snapshot in analysis/data/ into the numbers used in the paper.

Reads the files written by fetch_snapshot.py and writes

  data/stats.json   every number, machine-readable
  tables.md         the same numbers as the tables that appear in the paper

Only the Python standard library is used.
"""

import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data"

KEY_LABELS = {
    "4d848a97": "Pipeline bot (bioelectricitynexus.com)",
    "f3c0b0ba": "Author key 1 (J. Dietz)",
    "403d6743": "Author key 2 (J. Dietz)",
}

MODEL_LABELS = [
    ("gpt-5.6-sol", "GPT-5.6 Sol"),
    ("grok-4.7", "Grok 4.7"),
    ("gemini-4-argon", "Gemini 4 Argon"),
    ("claude-fable-5-1", "Claude Fable 5.1"),
    ("muse-wonder-1.0", "Muse Wonder 1.0"),
]


def read(name):
    with open(DATA / f"{name}.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def local(iri):
    return iri.rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]


def model_of(agent):
    for needle, label in MODEL_LABELS:
        if needle in agent:
            return label
    return local(agent)


def rubric_of(assessment_type):
    """'dataset-resolvability/0.2.0/data-adequacy' -> ('dataset-resolvability/0.2.0', 'data-adequacy')."""
    parts = assessment_type.split("/")
    if len(parts) >= 2:
        return "/".join(parts[:2]), "/".join(parts[2:])
    return assessment_type, ""


def pearson(xs, ys):
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    return sxy / math.sqrt(sxx * syy) if sxx and syy else float("nan")


def r(x, digits=3):
    return round(x, digits)


# --------------------------------------------------------------------------
# Network
# --------------------------------------------------------------------------

def network_stats():
    nanopubs = read("nanopubs")
    live = [n for n in nanopubs if n["live"] == "1"]

    by_key = {}
    for prefix, label in KEY_LABELS.items():
        rows = [n for n in nanopubs if n["pubkey"].startswith(prefix)]
        rows_live = [n for n in rows if n["live"] == "1"]
        by_key[prefix] = {
            "label": label,
            "nanopubs": len(rows),
            "live": len(rows_live),
            "first": min(n["created"] for n in rows)[:10],
            "last": max(n["created"] for n in rows)[:10],
        }

    by_month = Counter(n["created"][:7] for n in live)

    # Types: the same class exists in several namespace generations, so types
    # are counted by local name. One nanopublication can carry several types.
    by_type = Counter()
    for n in live:
        for t in {local(t) for t in n["types"].split("|") if t}:
            by_type[t] += 1
    untyped = sum(1 for n in live if not n["types"])

    # A partition by kind: every live nanopublication is counted once, under
    # the first kind that applies.
    def kind(n):
        types = {local(t) for t in n["types"].split("|") if t}
        if n["pubkey"].startswith("4d848a97"):
            return "pipeline statements, March-June 2026"
        if "LLMClaimAssessment" in types:
            return "model assessments"
        if "Claim" in types:
            return "claims"
        if "Concept" in types:
            return "concepts (incl. rubrics and their dimensions)"
        if types & {"Plan", "Activity"}:
            return "plans and activities"
        if "Dataset" in types:
            return "datasets"
        if "EvidenceItem" in types:
            return "evidence items (executed tests)"
        return "other (key declaration, profile image)"

    by_kind = Counter(kind(n) for n in live)
    claims_also_testable = sum(
        1 for n in live if {"Claim", "TestableHypothesis"} <= {local(t) for t in n["types"].split("|") if t})

    domains = defaultdict(lambda: {"nanopubs": 0, "claims": 0, "assessments": 0})
    for n in live:
        if not n["domain"]:
            continue
        d = domains[local(n["domain"])]
        d["nanopubs"] += 1
        types = {local(t) for t in n["types"].split("|") if t}
        if "Claim" in types:
            d["claims"] += 1
        if "LLMClaimAssessment" in types:
            d["assessments"] += 1

    return {
        "nanopubs": len(nanopubs),
        "live": len(live),
        "by_key": by_key,
        "live_by_month": dict(sorted(by_month.items())),
        "live_by_kind": dict(by_kind.most_common()),
        "claims_also_testable_hypotheses": claims_also_testable,
        "live_by_type": dict(by_type.most_common()),
        "live_without_type": untyped,
        "live_by_domain": dict(sorted(domains.items(), key=lambda kv: -kv[1]["nanopubs"])),
    }


def claim_stats():
    claims = read("claims")
    kinds = Counter(c["kind"] or "(none given)" for c in claims)
    return {
        "claim_nanopubs": len(claims),
        "distinct_claims": len({c["claim"] for c in claims}),
        "by_kind": dict(kinds.most_common()),
    }


def assessment_stats():
    rows = read("assessments")
    out = {"introduced_assessments": len(rows)}

    # Rubric scores: group by rubric (name/version) and model. Assessments of
    # one rubric dimension (MorphoEval publishes each dimension on its own)
    # are grouped under the rubric and reported per dimension.
    rubrics = defaultdict(lambda: defaultdict(list))
    verdicts = defaultdict(Counter)
    probabilities = defaultdict(list)
    for a in rows:
        model = model_of(a["agent"])
        if a["probability"]:
            probabilities[model].append(float(a["probability"]))
            continue
        rubric, dimension = rubric_of(a["assessmentType"])
        if a["score"]:
            rubrics[(rubric, dimension)][model].append(float(a["score"]))
        if a["verdict"] and not dimension:
            verdicts[rubric][a["verdict"]] += 1

    out["rubric_scores"] = [
        {"rubric": rubric, "dimension": dimension, "model": model, "n": len(scores), "mean": r(statistics.fmean(scores))}
        for (rubric, dimension), models in sorted(rubrics.items())
        for model, scores in sorted(models.items(), key=lambda kv: -len(kv[1]))
    ]
    out["verdicts"] = {rubric: dict(c.most_common()) for rubric, c in sorted(verdicts.items())}
    out["probability_assessments"] = {
        model: {"n": len(v), "mean": r(statistics.fmean(v))} for model, v in sorted(probabilities.items())
    }

    # All versions of a rubric together, per model.
    families = defaultdict(lambda: defaultdict(list))
    for a in rows:
        rubric, dimension = rubric_of(a["assessmentType"])
        if a["score"] and not a["probability"] and (not dimension or rubric.startswith("morphoeval")):
            if rubric.startswith("morphoeval") and dimension != "overall":
                continue
            families[rubric.split("/")[0]][model_of(a["agent"])].append(float(a["score"]))
    out["rubric_families"] = {
        family: {model: {"n": len(v), "mean": r(statistics.fmean(v))} for model, v in sorted(models.items(), key=lambda kv: -len(kv[1]))}
        for family, models in sorted(families.items())
    }

    # Agreement between models that scored the same claim on the same rubric.
    per_claim = defaultdict(dict)
    for a in rows:
        rubric, dimension = rubric_of(a["assessmentType"])
        if rubric.startswith("dataset-resolvability") and not dimension and a["claim"] and a["score"]:
            per_claim[(rubric, a["claim"])][model_of(a["agent"])] = (float(a["score"]), a["verdict"])
    pairs = defaultdict(list)
    for (rubric, _claim), models in per_claim.items():
        names = sorted(models)
        for i, m1 in enumerate(names):
            for m2 in names[i + 1:]:
                pairs[(m1, m2)].append((models[m1], models[m2]))
    out["resolvability_claims_assessed"] = len({claim for (_r, claim) in per_claim})
    out["resolvability_claims_with_two_or_more_models"] = sum(1 for m in per_claim.values() if len(m) >= 2)
    out["resolvability_agreement"] = [
        {
            "models": [m1, m2],
            "claims": len(p),
            "mean_scores": [r(statistics.fmean(a[0] for a, _ in p)), r(statistics.fmean(b[0] for _, b in p))],
            "mean_abs_score_difference": r(statistics.fmean(abs(a[0] - b[0]) for a, b in p)),
            "pearson_r": r(pearson([a[0] for a, _ in p], [b[0] for _, b in p])),
            "same_verdict_share": r(sum(1 for a, b in p if a[1] == b[1]) / len(p)),
        }
        for (m1, m2), p in sorted(pairs.items(), key=lambda kv: -len(kv[1]))
    ]

    # Resolvability per domain: how many claims, and how many of them every
    # assessing model judged resolvable with data that exist now.
    domain_of = {n["np"]: local(n["domain"]) for n in read("nanopubs") if n["domain"]}
    by_domain = defaultdict(lambda: defaultdict(list))
    for a in rows:
        rubric, dimension = rubric_of(a["assessmentType"])
        if rubric.startswith("dataset-resolvability") and not dimension and a["claim"] and a["score"]:
            by_domain[domain_of.get(a["np"], "(none)")][a["claim"]].append((float(a["score"]), a["verdict"]))
    out["resolvability_by_domain"] = {
        domain: {
            "claims": len(claims),
            "assessments": sum(len(v) for v in claims.values()),
            "mean_score": r(statistics.fmean(s for v in claims.values() for s, _ in v)),
            "resolvable_now_all_models": sum(1 for v in claims.values() if all(x == "resolvable-now" for _, x in v)),
            "resolvable_now_any_model": sum(1 for v in claims.values() if any(x == "resolvable-now" for _, x in v)),
            "not_empirically_resolvable_all_models": sum(1 for v in claims.values() if all(x == "not-empirically-resolvable" for _, x in v)),
        }
        for domain, claims in sorted(by_domain.items(), key=lambda kv: -len(kv[1]))
    }
    all_claims = [v for claims in by_domain.values() for v in claims.values()]
    out["resolvability_totals"] = {
        "claims": len(all_claims),
        "resolvable_now_all_models": sum(1 for v in all_claims if all(x == "resolvable-now" for _, x in v)),
        "resolvable_now_any_model": sum(1 for v in all_claims if any(x == "resolvable-now" for _, x in v)),
        "not_empirically_resolvable_all_models": sum(1 for v in all_claims if all(x == "not-empirically-resolvable" for _, x in v)),
    }

    dims = defaultdict(lambda: defaultdict(lambda: [0, 0.0]))
    for d in read("dimension_scores"):
        rubric, dimension = rubric_of(d["assessmentType"])
        if not rubric.startswith("dataset-resolvability"):
            continue
        cell = dims[dimension][model_of(d["agent"])]
        cell[0] += int(d["n"])
        cell[1] += int(d["n"]) * float(d["mean"])
    out["resolvability_dimension_means"] = {
        dimension: {model: r(total / n) for model, (n, total) in sorted(models.items())}
        for dimension, models in sorted(dims.items())
    }
    return out


def legacy_stats():
    rows = read("legacy_statements")
    # The same assessment appears under more than one legacy namespace; the
    # local name identifies it. Where two statements give different values
    # for one assessment, the one published last is used.
    stated = defaultdict(list)
    for s in rows:
        name = local(s["s"])
        if name.startswith("assessment-") and local(s["p"]).lower() in ("weightofevidence_deciban", "weightofevidencedeciban"):
            stated[name].append((s["created"], float(s["o"])))
    values = sorted(max(v)[1] for v in stated.values())
    conflicting = sum(1 for v in stated.values() if len({round(x, 2) for _, x in v}) > 1)
    most_common_value, most_common_n = Counter(values).most_common(1)[0]
    types = Counter(local(s["o"]) for s in rows if s["p"].endswith("#type"))
    return {
        "nanopubs": len({s["np"] for s in rows}),
        "statements": len(rows),
        "types_stated": dict(types.most_common()),
        "bayesian_assessments_with_deciban": len(values),
        "deciban_min": values[0],
        "deciban_median": statistics.median(values),
        "deciban_max": values[-1],
        "deciban_most_common_value": most_common_value,
        "deciban_most_common_count": most_common_n,
        "assessments_with_conflicting_values": conflicting,
        "last_published": max(s["created"] for s in rows)[:10],
    }


def test_stats():
    nanopubs = [n for n in read("nanopubs") if n["live"] == "1"]
    evidence = [n for n in nanopubs if "EvidenceItem" in {local(t) for t in n["types"].split("|") if t}]
    datasets = [n for n in nanopubs if "Dataset" in {local(t) for t in n["types"].split("|") if t}]
    revisions = [e for e in read("evidence_revisions") if e["revision"]]
    return {
        "evidence_item_nanopubs": len(evidence),
        "dataset_nanopubs": len(datasets),
        "evidence_items_with_revisions": len({e["evidence"] for e in revisions}),
        "recorded_revisions": len(revisions),
    }


# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------

def app_stats():
    with open(DATA / "app.json", encoding="utf-8") as f:
        app = json.load(f)
    domains = read("app_domains")
    for d in domains:
        for k in ("papers", "claims", "hypotheses"):
            d[k] = int(d[k])

    # Domain labels are slugs; their first token groups them into families
    # (math-..., electrochemical-..., gan-...).
    families = defaultdict(lambda: {"domains": 0, "papers": 0, "claims": 0, "hypotheses": 0})
    for d in domains:
        fam = families[d["domain"].split("-")[0]]
        fam["domains"] += 1
        for k in ("papers", "claims", "hypotheses"):
            fam[k] += d[k]
    top = sorted(families.items(), key=lambda kv: -kv[1]["domains"])
    shown, rest = top[:5], top[5:]
    other = {k: sum(f[k] for _, f in rest) for k in ("domains", "papers", "claims", "hypotheses")}

    return {
        "stats_endpoint": app["stats"],
        "domains": len(domains),
        "papers": sum(d["papers"] for d in domains),
        "claims": sum(d["claims"] for d in domains),
        "hypotheses": sum(d["hypotheses"] for d in domains),
        "domains_with_hypotheses": sum(1 for d in domains if d["hypotheses"] > 0),
        "median_papers_per_domain": statistics.median(d["papers"] for d in domains),
        "median_claims_per_domain": statistics.median(d["claims"] for d in domains),
        "publication_years": app["publication_years"],
        "domain_families": [dict(family=name, **f) for name, f in shown] + [dict(family="(other)", **other)],
        "economic": app["economic"],
    }


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def n(x):
    return f"{x:,}"


def write_tables(stats):
    net, cl, ass, leg, tests, app = (stats[k] for k in ("network", "claims", "assessments", "legacy", "tests", "app"))
    out = [f"# Snapshot of {stats['snapshot']['taken_at']}", ""]

    out += ["## Deployed graph (application)", ""]
    out += [table(["Domain family", "Domains", "Papers", "Hypotheses", "Claims"],
                  [[f["family"], n(f["domains"]), n(f["papers"]), n(f["hypotheses"]), n(f["claims"])] for f in app["domain_families"]]
                  + [["**Total**", n(app["domains"]), n(app["papers"]), n(app["hypotheses"]), n(app["claims"])]]), ""]
    eco = app["economic"]
    out += [f"- Domains with at least one hypothesis: {n(app['domains_with_hypotheses'])} of {n(app['domains'])}",
            f"- Median per domain: {app['median_papers_per_domain']:g} papers, {app['median_claims_per_domain']:g} claims",
            f"- Publication years: {app['publication_years'][0]}–{app['publication_years'][1]}",
            f"- Stats endpoint: {json.dumps(app['stats_endpoint'])}",
            f"- Economic forecasts: {n(eco['forecasts'])}, market sizes sum to ${eco['market_size_sum_billion_usd'] / 1000:,.1f} trillion, "
            f"mean {eco['mean_years_to_achievement']} years to achievement, largest single market ${eco['market_size_max_billion_usd']:g} billion",
            f"- Forecast sources: {json.dumps(eco['by_source'])}", ""]

    out += ["## Nanopublications by signing key", ""]
    out += [table(["Key", "Published", "Live", "First", "Last"],
                  [[f"{v['label']} `{k}…`", n(v["nanopubs"]), n(v["live"]), v["first"], v["last"]] for k, v in net["by_key"].items()]
                  + [["**Total**", n(net["nanopubs"]), n(net["live"]), "", ""]]), ""]
    out += ["Live nanopublications by month: " + ", ".join(f"{m}: {n(c)}" for m, c in net["live_by_month"].items()), ""]

    out += ["## Live nanopublications by kind (each counted once)", ""]
    out += [table(["Kind", "Nanopublications"], [[k, n(c)] for k, c in net["live_by_kind"].items()]
                  + [["**Total**", n(net["live"])]]), ""]
    out += [f"Claims that are also typed as testable hypotheses: {net['claims_also_testable_hypotheses']}", ""]
    out += ["## Live nanopublications by type", ""]
    out += [table(["Type (local name)", "Nanopublications"], [[t, n(c)] for t, c in net["live_by_type"].items()]
                  + [["(no type declared)", n(net["live_without_type"])]]), ""]

    out += ["## Live nanopublications by domain", ""]
    out += [table(["Domain", "Nanopublications", "Claims", "Assessments"],
                  [[d, n(v["nanopubs"]), n(v["claims"]), n(v["assessments"])] for d, v in net["live_by_domain"].items()]), ""]

    out += ["## Claims", "", f"{n(cl['claim_nanopubs'])} claim nanopublications, {n(cl['distinct_claims'])} distinct claims.", ""]
    out += [table(["Kind (dcterms:type)", "Claims"], [[k, n(c)] for k, c in cl["by_kind"].items()]), ""]

    out += ["## Rubric assessments", ""]
    out += [table(["Rubric", "Dimension", "Model", "Assessments", "Mean score"],
                  [[x["rubric"], x["dimension"] or "(overall)", x["model"], n(x["n"]), f"{x['mean']:.2f}"] for x in ass["rubric_scores"]]), ""]
    out += ["All versions of a rubric together (overall scores):", ""]
    out += [table(["Rubric", "Model", "Assessments", "Mean score"],
                  [[fam, model, n(v["n"]), f"{v['mean']:.2f}"] for fam, models in ass["rubric_families"].items() for model, v in models.items()]), ""]
    out += ["Verdicts:", ""]
    out += [table(["Rubric", "Verdict", "Assessments"],
                  [[rub, v, n(c)] for rub, vs in ass["verdicts"].items() for v, c in vs.items()]), ""]
    out += [f"Claims with a dataset-resolvability assessment: {n(ass['resolvability_claims_assessed'])}; "
            f"claim–rubric pairs scored by two or more models: {n(ass['resolvability_claims_with_two_or_more_models'])}.", ""]
    out += [table(["Model pair", "Claims", "Mean scores on these claims", "Mean abs. score difference", "Pearson r", "Same verdict"],
                  [[" vs. ".join(x["models"]), n(x["claims"]), " vs. ".join(f"{m:.2f}" for m in x["mean_scores"]),
                    f"{x['mean_abs_score_difference']:.2f}", f"{x['pearson_r']:.2f}",
                    f"{100 * x['same_verdict_share']:.0f}%"] for x in ass["resolvability_agreement"]]), ""]
    out += ["Dataset resolvability by domain (a claim counts as resolvable now when every model that scored it says so):", ""]
    tot = ass["resolvability_totals"]
    out += [table(["Domain", "Claims", "Assessments", "Mean score", "Resolvable now (all models)", "Resolvable now (any model)", "Not empirically resolvable (all models)"],
                  [[d, n(v["claims"]), n(v["assessments"]), f"{v['mean_score']:.2f}", n(v["resolvable_now_all_models"]), n(v["resolvable_now_any_model"]),
                    n(v["not_empirically_resolvable_all_models"])] for d, v in ass["resolvability_by_domain"].items()]
                  + [["**Total**", n(tot["claims"]), "", "", n(tot["resolvable_now_all_models"]), n(tot["resolvable_now_any_model"]),
                      n(tot["not_empirically_resolvable_all_models"])]]), ""]
    models = sorted({m for v in ass["resolvability_dimension_means"].values() for m in v})
    out += ["Dataset-resolvability dimension means (both versions):", ""]
    out += [table(["Dimension"] + models,
                  [[d] + [f"{v[m]:.2f}" if m in v else "" for m in models] for d, v in ass["resolvability_dimension_means"].items()]), ""]
    out += ["Probability assessments (delphi:hasProbability):", ""]
    out += [table(["Model", "Assessments", "Mean probability"],
                  [[m, n(v["n"]), f"{v['mean']:.2f}"] for m, v in ass["probability_assessments"].items()]), ""]

    out += ["## Bayesian assessments (March–June 2026 pipeline key)", ""]
    out += [f"- {n(leg['nanopubs'])} nanopublications, {n(leg['statements'])} statements, last published {leg['last_published']}",
            f"- Assessments with a weight of evidence in decibans: {leg['bayesian_assessments_with_deciban']}",
            f"- Range {leg['deciban_min']:.1f}–{leg['deciban_max']:.1f} deciban, median {leg['deciban_median']:.1f}",
            f"- Most common value: {leg['deciban_most_common_value']:.2f} deciban, in {leg['deciban_most_common_count']} assessments",
            f"- Assessments stated with two different values: {leg['assessments_with_conflicting_values']}",
            f"- Types stated: {json.dumps(leg['types_stated'])}", ""]

    out += ["## Executed tests", ""]
    out += [f"- Evidence-item nanopublications: {tests['evidence_item_nanopubs']}",
            f"- Dataset nanopublications: {tests['dataset_nanopubs']}",
            f"- Evidence items with recorded revisions: {tests['evidence_items_with_revisions']} ({tests['recorded_revisions']} revisions)", ""]

    (HERE / "tables.md").write_text("\n".join(out), encoding="utf-8")


def main():
    with open(DATA / "snapshot.json", encoding="utf-8") as f:
        snapshot = json.load(f)
    stats = {
        "snapshot": snapshot,
        "app": app_stats(),
        "network": network_stats(),
        "claims": claim_stats(),
        "assessments": assessment_stats(),
        "legacy": legacy_stats(),
        "tests": test_stats(),
    }
    with open(DATA / "stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
        f.write("\n")
    write_tables(stats)
    print("wrote", DATA / "stats.json", "and", HERE / "tables.md")


if __name__ == "__main__":
    main()
