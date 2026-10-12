"""
Compares the Streamlit badge's "Actionable Items" with the shared loader's.

    .venv/Scripts/python diagnostics/check_actionable_parity.py

Two code paths count a module's outstanding items:

- `app.py::load_checklist_data()` feeds the badge on School Dashboard and
  Faculty Overview. It builds its own lean module row.
- `loaders.load_audit_summaries()` feeds the Django School Dashboard. It uses
  the full module record, the same one the module report reads.

They should agree. Run on 12-10-2026 they did not, for 153 of 766 modules, by
exactly one each, and every one was the SGA rule: a module the SGA tool lists
with no attributes mapped is a pending finding ("Visible, no SGAs mapped"), but
the lean row carries no SGA data, so the badge never sees it. CLAUDE.md says
the rule applies to Actionable Items; the module report applies it; the badge
does not. This script reports any difference and whether the SGA rule explains
it, so a new, unexplained one is visible.

app.py is not imported (that would start Streamlit): the function's source is
extracted and run as written. Read-only.
"""

import ast
import logging
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
logging.disable(logging.CRITICAL)

import pandas as pd  # noqa: E402

import database  # noqa: E402
import loaders  # noqa: E402
import processing  # noqa: E402


def streamlit_badge():
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "load_checklist_data")
    fn.decorator_list = []
    ns = dict(pd=pd, logging=logging, table_exists=database.table_exists,
              CURRENT_ACADEMIC_YEAR=processing.CURRENT_ACADEMIC_YEAR)
    exec(compile(ast.Module([fn], []), "app.py", "exec"), ns)
    return ns["load_checklist_data"]()


def main():
    badge = streamlit_badge()
    sources = loaders.load_module_sources()
    with database.get_db_connection() as conn:
        df_sits = pd.read_sql_query("SELECT * FROM sits_assessment_2026_27", conn)
    df_aut, df_spr = loaders.assemble_module_frames(df_sits, sources)
    rows = {}
    for df in (df_aut, df_spr):
        for record in df.to_dict("records"):
            rows.setdefault(record["New module code"], record)

    fields = database.get_active_audit_fields()
    shared = loaders.load_audit_summaries(rows, fields)

    differ = [(c, badge.get(c, {}).get("Actionable Items", 0), shared[c]["Actionable Items"])
              for c in rows if badge.get(c, {}).get("Actionable Items", 0)
              != shared[c]["Actionable Items"]]
    print(f"{len(rows)} modules compared; {len(rows) - len(differ)} agree, {len(differ)} differ.")

    unexplained = []
    why = Counter()
    for code, was, now in differ:
        responses = shared[code]["Responses"]
        use = fields if responses else []
        row = rows[code]
        without_sga = dict(row, **{"SGA Attributes": None})
        extra = ({(f["source"], f.get("label")) for f in processing.derive_module_findings(
                     row, responses, use) if f["state"] == "pending"}
                 - {(f["source"], f.get("label")) for f in processing.derive_module_findings(
                     without_sga, responses, use) if f["state"] == "pending"})
        if now - was == 1 and len(extra) == 1 and row.get("SGA Attributes") == 0:
            why["SGA rule: 'Visible, no SGAs mapped'"] += 1
        else:
            unexplained.append((code, was, now))
    for reason, n in why.items():
        print(f"  {n} explained by {reason}")
    if unexplained:
        print(f"  {len(unexplained)} UNEXPLAINED, first few: {unexplained[:5]}")
        sys.exit(1)
    print("Every difference is explained.")


if __name__ == "__main__":
    main()
