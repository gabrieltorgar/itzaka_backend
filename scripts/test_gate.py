#!/usr/bin/env python3
"""
test_gate.py — merge quality gate: every executed test passes AND line coverage reaches --min.

  # backend (pytest + pytest-cov)
  python3 scripts/test_gate.py --junit reports/junit.xml --cobertura reports/coverage.xml \
      --allow-skip-reason 'got empty parameter set'
  # frontend (vitest + @vitest/coverage-v8 with the lcov reporter)
  python3 scripts/test_gate.py --junit reports/junit.xml --lcov coverage/lcov.info
  # mobile (flutter test --coverage --file-reporter json:reports/flutter.json)
  python3 scripts/test_gate.py --flutter-json reports/flutter.json --lcov coverage/lcov.info \
      --exclude '*.g.dart' --exclude '*.freezed.dart'

Tests: at least one executed and none failing (errors count as failures). Skipped tests block too: an xfail
(JUnit <skipped type="pytest.xfail">) always blocks, and any other skip blocks unless its message contains a
--allow-skip-reason text (repeatable; the backend allows pytest's 'got empty parameter set', the fresh
scaffold's empty admin registry) or the non-allowed skips are at most --max-skipped (default 0). Each
blocking skip is listed as file::test.
Coverage: line coverage summed over every coverage report — lcov (DA lines, else LF/LH) or
Cobertura XML (lines-valid/lines-covered, else its <line> elements). --exclude drops lcov source
files whose path matches a glob. --min takes a fraction (0.90) or a percentage (90); default
$MIN_COVERAGE or 0.90; the flow's floor is 90 % and a lower minimum is refused (a higher one is fine).
Exit 0 = passed · 1 = blocked (failing tests, no tests, blocking skips, coverage below --min) ·
2 = missing or unreadable report, or --min below the 90 % floor. The summary line also goes to
$GITHUB_STEP_SUMMARY.
"""
import argparse, fnmatch, json, os, sys
import xml.etree.ElementTree as ET

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

FLOOR = 0.90


def junit_counts(path):
    """(passed, failed, skips) — skips: [(name, message, is_xfail)]."""
    root = ET.parse(path).getroot()
    passed = failed = 0
    skips = []
    for case in root.iter("testcase"):
        tags = {child.tag for child in case}
        if "failure" in tags or "error" in tags:
            failed += 1
        elif "skipped" in tags:
            sk = case.find("skipped")
            where = case.get("file") or case.get("classname") or "?"
            message = (sk.get("message") or "") + " " + (sk.text or "")
            skips.append((f"{where}::{case.get('name', '?')}", message.strip(), sk.get("type") == "pytest.xfail"))
        else:
            passed += 1
    return passed, failed, skips


def flutter_counts(path):
    passed = failed = 0
    skips, tests, suites = [], {}, {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = ev.get("type")
            if kind == "suite":
                suites[ev["suite"].get("id")] = ev["suite"].get("path") or "?"
            elif kind == "testStart":
                tests[ev["test"].get("id")] = ev["test"]
            if kind != "testDone" or ev.get("hidden"):
                continue
            if ev.get("skipped"):
                t = tests.get(ev.get("testID"), {})
                reason = (t.get("metadata") or {}).get("skipReason") or ""
                skips.append((f"{suites.get(t.get('suiteID'), '?')}::{t.get('name', '?')}", reason, False))
            elif ev.get("result") == "success":
                passed += 1
            else:
                failed += 1
    return passed, failed, skips


def lcov_lines(path, excludes):
    totals = {"found": 0, "hit": 0}
    rec = {"sf": None, "da": {}, "lf": None, "lh": None}

    def flush():
        sf = rec["sf"]
        if sf is None or any(fnmatch.fnmatch(sf.replace("\\", "/"), pat) for pat in excludes):
            return
        if rec["da"]:
            totals["found"] += len(rec["da"])
            totals["hit"] += sum(1 for c in rec["da"].values() if c > 0)
        elif rec["lf"] is not None:
            totals["found"] += rec["lf"]
            totals["hit"] += rec["lh"] or 0

    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if line.startswith("SF:"):
                rec.update(sf=line[3:], da={}, lf=None, lh=None)
            elif line.startswith("DA:"):
                parts = line[3:].split(",")
                try:
                    n, c = int(parts[0]), int(float(parts[1]))
                except (ValueError, IndexError):
                    continue
                rec["da"][n] = max(rec["da"].get(n, 0), c)
            elif line.startswith("LF:"):
                rec["lf"] = int(line[3:] or 0)
            elif line.startswith("LH:"):
                rec["lh"] = int(line[3:] or 0)
            elif line == "end_of_record":
                flush()
                rec["sf"] = None
    flush()
    return totals["found"], totals["hit"]


def cobertura_lines(path):
    root = ET.parse(path).getroot()
    valid, covered = root.get("lines-valid"), root.get("lines-covered")
    if valid is not None and covered is not None:
        return int(float(valid)), int(float(covered))
    found = hit = 0
    seen = set()
    for cls in root.iter("class"):
        fname = cls.get("filename", "")
        for ln in cls.iter("line"):
            key = (fname, ln.get("number"))
            if key in seen:
                continue
            seen.add(key)
            found += 1
            if int(float(ln.get("hits", "0"))) > 0:
                hit += 1
    return found, hit


def main(argv=None):
    ap = argparse.ArgumentParser(description="Quality gate: pruebas en verde y cobertura mínima")
    ap.add_argument("--junit", action="append", default=[])
    ap.add_argument("--flutter-json", action="append", default=[])
    ap.add_argument("--lcov", action="append", default=[])
    ap.add_argument("--cobertura", action="append", default=[])
    ap.add_argument("--exclude", action="append", default=[], help="glob de archivos a excluir del lcov")
    ap.add_argument("--min", type=float, default=float(os.environ.get("MIN_COVERAGE", "0.90")))
    ap.add_argument("--max-skipped", type=int, default=0, help="omitidas sin motivo permitido que se toleran (default 0)")
    ap.add_argument("--allow-skip-reason", action="append", default=[], help="texto que, en el motivo, permite una omisión")
    a = ap.parse_args(argv)
    if not (a.junit or a.flutter_json):
        ap.error("indica el reporte de pruebas (--junit o --flutter-json)")
    if not (a.lcov or a.cobertura):
        ap.error("indica el reporte de cobertura (--lcov o --cobertura)")
    minimum = a.min / 100 if a.min > 1 else a.min
    if minimum + 1e-9 < FLOOR:
        print(f"QUALITY_GATE BLOQUEADO: mínimo por debajo del piso del flujo (90 %): --min {minimum:.0%}")
        return 2
    passed = failed = found = hit = 0
    skips = []
    try:
        for path in a.junit:
            p, f, s = junit_counts(path); passed += p; failed += f; skips += s
        for path in a.flutter_json:
            p, f, s = flutter_counts(path); passed += p; failed += f; skips += s
        for path in a.lcov:
            fo, hi = lcov_lines(path, a.exclude); found += fo; hit += hi
        for path in a.cobertura:
            fo, hi = cobertura_lines(path); found += fo; hit += hi
    except (OSError, ET.ParseError, ValueError, KeyError) as e:
        print(f"QUALITY_GATE BLOQUEADO: reporte faltante o ilegible ({e})")
        return 2
    allowed = [t.lower() for t in a.allow_skip_reason if t.strip()]
    xfails = [s for s in skips if s[2]]
    unexplained = [s for s in skips if not s[2] and not any(t in s[1].lower() for t in allowed)]
    executed = passed + failed
    coverage = hit / found if found else 0.0
    reasons = []
    if executed == 0:
        reasons.append("no se ejecutó ninguna prueba")
    if failed:
        reasons.append(f"{failed} prueba(s) en rojo")
    if xfails:
        reasons.append(f"{len(xfails)} xfail (siempre bloquea: corrige la prueba o el código)")
    if len(unexplained) > a.max_skipped:
        reasons.append(f"{len(unexplained)} prueba(s) omitida(s) sin motivo permitido (máximo {a.max_skipped})")
    if found == 0:
        reasons.append("el reporte de cobertura no midió ninguna línea")
    elif coverage + 1e-9 < minimum:
        reasons.append(f"cobertura {coverage:.1%} menor al mínimo {minimum:.0%}")
    ok = not reasons
    msg = (f"QUALITY_GATE {'OK' if ok else 'BLOQUEADO'}: {passed}/{executed} pruebas pasan · "
           f"cobertura {coverage:.1%} ({hit}/{found} líneas; mínimo {minimum:.0%}) · {len(skips)} omitidas")
    if reasons:
        msg += " — " + "; ".join(reasons)
    print(msg)
    blocking = xfails + (unexplained if len(unexplained) > a.max_skipped else [])
    for name, reason, is_xfail in blocking:
        print(f"  {'xfail' if is_xfail else 'omitida'}: {name}" + (f" — {reason}" if reason else ""))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(msg + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
