"""BeautyMind AI UI v2: modern card-based design + starter routines from a skin scan (works with or without owned products)."""
import os, html, inspect, numpy as np, pandas as pd, gradio as gr
from PIL import Image
from bm_config import P, get_conn
from bm_ml import CATS, STORAGES, CLIMATES
from bm_alerts import run_user
import bm_routine as BR
import bm_dash as D
from bm_skin import analyze, save_scan
from bm_recommend import make_fill, LOOK
from bm_app import (SKIN, LIFESTYLES, CONCERNS, ALLERGENS, user_row, inventory, load_user, create_profile, update_profile,
                    add_product, delete_product, score_html, add_demo, do_dash)

SEVC = {"Critical": "#e11d48", "High": "#f97316", "Medium": "#f59e0b", "Low": "#10b981"}
PRIC = {"High": "#e11d48", "Medium": "#f59e0b", "Low": "#10b981", "Discard": "#6b7280"}
E = lambda s: html.escape(str(s))
chip = lambda t, c: f'<span class="chip" style="--c:{c}">{E(t)}</span>'

CSS = """
:root{--bm1:#e11d48;--bm2:#7c3aed;--bd:var(--border-color-primary)}
.gradio-container{max-width:1200px!important;margin:auto!important}
footer{display:none!important}
.hero{padding:28px 32px;border-radius:24px;color:#fff;background:linear-gradient(120deg,#e11d48,#a21caf 55%,#6d28d9);box-shadow:0 12px 32px #7c3aed44;position:relative;overflow:hidden}
.hero:after{content:"";position:absolute;right:-70px;top:-70px;width:260px;height:260px;border-radius:50%;background:#ffffff1f}
.hero h1{margin:0;font-size:32px;font-weight:800;letter-spacing:-.5px;color:#fff}.hero p{margin:6px 0 14px;opacity:.93;color:#fff}
.pill{display:inline-block;margin:3px 6px 0 0;padding:4px 12px;border-radius:999px;background:#ffffff2b;font-size:12px}
.steps{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0}
.step{flex:1;min-width:210px;padding:14px 16px;border-radius:16px;border:1px solid var(--bd);background:var(--background-fill-primary)}
.step b,.no{display:inline-flex;flex:none;width:26px;height:26px;border-radius:50%;background:linear-gradient(135deg,var(--bm1),var(--bm2));color:#fff;align-items:center;justify-content:center;font-size:13px;margin-right:8px}
button[role=tab]{border-radius:999px!important;padding:8px 16px!important;font-weight:600!important;border:none!important}
button[role=tab][aria-selected=true]{background:linear-gradient(120deg,var(--bm1),var(--bm2))!important;color:#fff!important}
div[role=tablist]{border-bottom:none!important;gap:6px;flex-wrap:wrap}
.card{padding:16px 18px;border-radius:18px;border:1px solid var(--bd);background:var(--background-fill-primary);box-shadow:0 2px 12px #0000000d}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px}
.chip{display:inline-block;padding:2px 10px;border-radius:999px;font-size:11px;font-weight:600;background:color-mix(in srgb,var(--c) 16%,transparent);color:var(--c)}
.bar{height:8px;border-radius:99px;background:color-mix(in srgb,var(--c) 18%,transparent);overflow:hidden}.bar i{display:block;height:100%;background:var(--c);border-radius:99px}
.acard{padding:12px 14px;border-radius:14px;border:1px solid var(--bd);border-left:5px solid var(--c);background:var(--background-fill-primary);margin:8px 0}
.muted{color:var(--body-text-color-subdued);font-size:12.5px}
.st{display:flex;gap:10px;padding:12px 0;border-bottom:1px dashed var(--bd)}.st:last-child{border:0}
table.wk{width:100%;border-collapse:collapse;font-size:12.5px}.wk th{text-align:left;padding:8px;color:#fff;background:linear-gradient(120deg,var(--bm1),var(--bm2))}
.wk td{padding:8px;border-bottom:1px solid var(--bd);vertical-align:top}
.banner{padding:14px 16px;border-radius:14px;margin:6px 0;border:1px solid var(--bd);background:color-mix(in srgb,var(--bm2) 8%,transparent)}
"""
HERO = ('<div class="hero"><h1>✨ BeautyMind AI</h1><p>Explainable decision support for cosmetic expiry management and personalised skincare routines</p>'
        + "".join(f'<span class="pill">{t}</span>' for t in ["📸 Skin analysis", "🔥 Grad-CAM", "🔍 SHAP explanations", "🧪 Ingredient rule engine", "🧴 Starter routines"]) + "</div>")
STEPS = ('<div class="steps"><div class="step"><b>1</b>Create your profile</div><div class="step"><b>2</b>Scan your face</div>'
         '<div class="step"><b>3</b>Get your routine, with or without your own products</div></div>')
EMPTY_INV = '<div class="card">🧴 No products yet. Add some in the <b>Profile</b> tab, or scan your face and get a <b>starter routine with suggested products</b>.</div>'

def has_products(uid):
    user_row(uid)
    with get_conn() as c: return c.execute("SELECT COUNT(*) FROM products WHERE user_id=?", (int(uid),)).fetchone()[0] > 0

# ---------- alerts & priority
def alerts_html(al):
    if al.empty: return '<div class="card">✅ No alerts. Your inventory looks healthy.</div>'
    top = " ".join(chip(f"{s}: {n}", SEVC[s]) for s, n in al.severity.value_counts().items())
    cards = "".join(f'<div class="acard" style="--c:{SEVC[r.severity]}">{chip(r.alert_type, SEVC[r.severity])} <span class="muted">{r.severity}</span><div style="margin-top:6px">{E(r.message)}</div></div>' for r in al.itertuples())
    return f'<div class="card"><b>{len(al)} alerts</b> &nbsp;{top}</div>{cards}'

def prio_html(rk):
    cards = "".join(
        f'<div class="card"><div style="display:flex;justify-content:space-between;gap:8px"><b>{E(r.name)}</b>{chip(r.priority, PRIC[r.priority])}</div>'
        f'<div class="muted">{E(r.category)} · {int(r.days_left)} days left · waste risk {int(r.waste_pct)}% · confidence {int(r.confidence)}%</div>'
        f'<div class="bar" style="--c:{PRIC[r.priority]};margin:10px 0"><i style="width:{int(min(r.days_left, 90) / 90 * 100)}%"></i></div>'
        f'<div style="font-size:13px">{E(r.reason)}</div></div>' for r in rk.itertuples())
    return f'<div class="grid">{cards}</div>'

def alerts_v2(uid):
    if not has_products(uid): return EMPTY_INV, "", "_Add products to see explanations._"
    rk, al = run_user(int(uid), explain_high=True, save=True)
    why = "\n".join(f"- **{r['name']}**: {r['why_ml']}" for _, r in rk[rk.priority == "High"].iterrows() if r["why_ml"]) or "_No High-priority products._"
    return alerts_html(al), prio_html(rk), why

# ---------- skin scan
def scan_v2(uid, img, save):
    user_row(uid)
    if img is None: raise gr.Error("Upload or capture a face photo first.")
    try: res = analyze(img)
    except Exception as e: raise gr.Error(f"Skin analysis failed: {e}")
    if "no face" in res["face_method"]: gr.Warning("No face detected: the whole image was used, so results are unreliable.")
    if save: save_scan(int(uid), res, img)
    md = ("\n".join("- " + w for w in res["why"]) + "\n\n_Cosmetic guidance only, not a medical diagnosis. Skin type and acne come from CNNs trained on small public datasets; "
          "pigmentation, redness and hydration are heuristic image-analysis estimates._")
    cta = '<div class="banner">✅ Scan complete. Click <b>Build my routine from this scan</b>: you get a full routine even if you have added no products.</div>'
    return (res["imgs"]["face"], res["imgs"]["gc_type"], res["imgs"]["gc_acne"], score_html(res), md,
            {k: res[k] for k in ("skin_type", "acne", "pigmentation", "redness", "hydration", "overall")}, cta)

# ---------- routine (owned products + suggestions)
def _step(n, it):
    sug = it["product_id"] < 0
    return (f'<div class="st"><div class="no">{n}</div><div><div class="muted" style="text-transform:uppercase;letter-spacing:.5px">{E(it["category"])}</div>'
            f'<div><b>{E(it["name"])}</b> {chip("✨ Suggested", "#7c3aed") if sug else ""} {chip(it["days"], "#0ea5e9")}</div>'
            + (f'<div class="muted">Look for: {E(LOOK.get(it["product_id"], ""))}</div>' if sug else "")
            + f'<div style="font-size:13px;margin-top:4px">{E(it["reason"])}</div></div></div>')

def routine_html(R):
    def col(title, slot):
        st = [x for x in R["items"] if x["slot"] == slot]
        return f'<div class="card"><h3 style="margin:0 0 6px">{title}</h3>' + ("".join(_step(n, x) for n, x in enumerate(st, 1)) or '<div class="muted">No steps.</div>') + "</div>"
    return f'<div class="cols">{col("☀️ Morning", "AM")}{col("🌙 Evening", "PM")}</div>'

def grid_html(g):
    rows = "".join(f"<tr><td><b>{d}</b></td><td>{E(r.AM) or '-'}</td><td>{E(r.PM) or '-'}</td></tr>" for d, r in g.iterrows())
    return f'<div class="card" style="overflow-x:auto"><table class="wk"><tr><th>Day</th><th>Morning</th><th>Evening</th></tr>{rows}</table></div>'

def routine_v2(uid, use_scan, scan):
    u = user_row(uid); uid = int(uid)
    sc = scan if (use_scan and scan) else (BR.latest_scan(uid) if use_scan else None)
    override = None if (sc is None or u["skin_type"] == "Sensitive") else str(sc["skin_type"])   # a photo cannot detect "Sensitive", so keep that profile
    R = BR.build_routine(uid, use_scan=use_scan, scan=sc, skin_override=override, fill=make_fill())
    bad = BR.validate(R, R["user"]["allergies"]); BR.save_routine(uid, R)
    ids = {i["product_id"] for i in R["items"]}; n_sug = sum(p < 0 for p in ids); n_own = len(ids) - n_sug
    if n_own == 0: how = "✨ <b>Starter routine</b>: you have no usable products yet, so these are suggestions based on " + ("your skin scan and profile." if sc is not None else "your profile. Run a Skin Analysis for more personalised picks.")
    elif n_sug: how = f"🧴 Built from <b>{n_own}</b> of your products plus <b>{n_sug}</b> suggestions to fill gaps."
    else: how = f"🧴 Built entirely from your {n_own} products."
    if override and override != u["skin_type"]: how += f" Skin type taken from your scan: <b>{E(override)}</b> (profile: {E(u['skin_type'])})."
    if any("Retinol" in LOOK.get(p, "") for p in ids): R["notes"].append("Retinol: avoid during pregnancy or breastfeeding, start slowly and always wear sunscreen in the morning.")
    if n_sug: R["notes"].append("Suggestions are generic product types matched by ingredients, not brand endorsements. Check the full ingredient list and patch-test anything new.")
    safe = "✅ Safety check passed: no expired or allergen products and no High/Medium ingredient clashes in the same slot." if not bad else "⚠️ Check failed: " + "; ".join(bad[:3])
    concerns = " ".join(chip(c, "#e11d48") for c in R["user"]["concerns"]) or '<span class="muted">none listed</span>'
    hdr = f'<div class="banner">{how}<div style="margin-top:8px"><b>Concerns considered:</b> {concerns}</div><div class="muted" style="margin-top:6px">{safe}</div></div>'
    ex = [e for e in R["excluded"] if e["product_id"] >= 0]
    exh = ('<div class="grid">' + "".join(f'<div class="card"><b>{E(e["name"])}</b> {chip(e["kind"], "#6b7280")}<div class="muted" style="margin-top:4px">{E(e["reason"])}</div></div>' for e in ex) + "</div>") if ex else '<div class="muted">Nothing excluded.</div>'
    notes = "".join(f'<div class="acard" style="--c:#7c3aed">{E(n)}</div>' for n in R["notes"]) or '<div class="muted">No notes.</div>'
    return hdr, routine_html(R), grid_html(R["grid"]), exh, notes

# ---------- dashboard
def dash_v2(uid):
    if has_products(uid): return do_dash(uid)
    sc = D.get_scans(uid); e = D._empty("Add products to see inventory analytics")
    return EMPTY_INV, e, e, e, e, D.fig_trend(sc), D.trend_md(sc)

def build_app():
    theme = gr.themes.Soft(primary_hue="rose", secondary_hue="violet", neutral_hue="slate", font=[gr.themes.GoogleFont("Inter"), "sans-serif"], radius_size="lg")
    kw = dict(theme=theme, css=CSS); in_blocks = "theme" in inspect.signature(gr.Blocks.__init__).parameters   # Gradio 6 moved theme/css to launch()
    with gr.Blocks(title="BeautyMind AI", **(kw if in_blocks else {})) as demo:
        gr.HTML(HERO); gr.HTML(STEPS); scan_state = gr.State(None)
        with gr.Row(equal_height=True):
            uid = gr.Number(value=1, precision=0, label="User ID (1-400 are demo users; create a profile for a new one)", scale=3); load = gr.Button("Load user", variant="primary", scale=1)
        with gr.Tabs() as tabs:
            with gr.Tab("👤 Profile & Inventory", id="profile"):
                prof = gr.HTML(); inv = gr.Dataframe(label="My cosmetics", interactive=False, wrap=True)
                with gr.Accordion("Create or edit profile", open=False):
                    with gr.Row(): name = gr.Textbox(label="Name"); age = gr.Slider(16, 80, value=28, step=1, label="Age")
                    with gr.Row():
                        skin = gr.Dropdown(SKIN, value="Combination", label="Skin type"); clim = gr.Dropdown(CLIMATES, value="Humid", label="Climate")
                        life = gr.Dropdown(LIFESTYLES, value=LIFESTYLES[0], label="Lifestyle")
                    con = gr.CheckboxGroup(CONCERNS, label="Concerns"); alg = gr.CheckboxGroup(ALLERGENS, label="Allergies")
                    oth = gr.Textbox(label="Other allergens (comma-separated ingredient names)")
                    with gr.Row(): b_new = gr.Button("Create new profile", variant="primary"); b_upd = gr.Button("Update this profile")
                with gr.Accordion("Add or remove a product (optional)", open=False):
                    with gr.Row(): p_name = gr.Textbox(label="Product name"); p_brand = gr.Textbox(label="Brand"); p_cat = gr.Dropdown(CATS, value="Serum", label="Category")
                    p_ing = gr.Textbox(label="Ingredients (comma-separated, e.g. Water, Glycerin, Retinol, Phenoxyethanol)", lines=2)
                    with gr.Row():
                        p_open = gr.Textbox(value=pd.Timestamp.today().strftime("%Y-%m-%d"), label="Open date (YYYY-MM-DD)"); p_pao = gr.Slider(3, 36, value=12, step=1, label="PAO (months)")
                        p_sto = gr.Dropdown(STORAGES, value="Drawer", label="Storage")
                    with gr.Row(): p_qty = gr.Slider(0, 100, value=100, label="Amount left %"); p_use = gr.Slider(0, 14, value=7, step=.5, label="Uses per week")
                    b_add = gr.Button("Add product", variant="primary")
                    with gr.Row(): del_id = gr.Number(label="Product ID to remove", precision=0); b_del = gr.Button("Remove product")
            with gr.Tab("🔔 Alerts & Priority", id="alerts"):
                b_al = gr.Button("Analyze my inventory", variant="primary"); al_html = gr.HTML(); pr_html = gr.HTML()
                with gr.Accordion("Why the model thinks so (SHAP drivers for High-priority products)", open=False): md_why = gr.Markdown()
                with gr.Accordion("Global SHAP: what drives shelf-life predictions", open=False), gr.Row():
                    for f in ("shap_summary", "shap_bar"):
                        fp = f"{P['outputs']}/{f}.png"
                        if os.path.exists(fp): gr.Image(value=np.asarray(Image.open(fp).convert("RGB")), interactive=False, show_label=False)
            with gr.Tab("📸 Skin Analysis", id="skin"):
                with gr.Row():
                    with gr.Column(scale=1):
                        img = gr.Image(label="Face photo (front-facing, good light)", type="numpy", sources=["upload", "webcam"])
                        sv = gr.Checkbox(True, label="Save scores to my history"); b_sk = gr.Button("Analyze skin", variant="primary"); sc_html = gr.HTML()
                    with gr.Column(scale=2):
                        cta = gr.HTML(); b_go = gr.Button("✨ Build my routine from this scan", variant="primary")
                        with gr.Accordion("Why these results", open=True): sk_md = gr.Markdown()
                        with gr.Accordion("Grad-CAM: where the AI looked", open=False), gr.Row():
                            o1 = gr.Image(label="Skin region used"); o2 = gr.Image(label="Skin type"); o3 = gr.Image(label="Acne")
            with gr.Tab("🧴 Routine", id="routine"):
                with gr.Row(): us = gr.Checkbox(True, label="Use my skin scan"); b_rt = gr.Button("Generate my routine", variant="primary")
                r_hdr = gr.HTML(); r_body = gr.HTML()
                with gr.Accordion("📅 Weekly plan", open=True): r_grid = gr.HTML()
                with gr.Accordion("Not used, and why", open=False): r_ex = gr.HTML()
                with gr.Accordion("Notes and tips", open=True): r_notes = gr.HTML()
            with gr.Tab("📊 Dashboard", id="dash"):
                with gr.Row(): b_db = gr.Button("Refresh dashboard", variant="primary"); b_demo = gr.Button("Add demo skin history (synthetic)")
                kpi = gr.HTML()
                with gr.Row(): p1 = gr.Plot(); p2 = gr.Plot()
                with gr.Row(): p3 = gr.Plot(); p4 = gr.Plot()
                p5 = gr.Plot(); tr_md = gr.Markdown()
        gr.Markdown("_Research prototype, not a medical device. Shelf-life data is synthetic. Skin scores are cosmetic guidance only. Routine rules are editable heuristics._")
        outs = [prof, inv, name, age, skin, clim, life, con, alg, oth]; r_outs = [r_hdr, r_body, r_grid, r_ex, r_notes]
        load.click(load_user, uid, outs); demo.load(load_user, uid, outs)
        b_new.click(create_profile, [name, age, skin, clim, life, con, alg, oth], uid).then(load_user, uid, outs)
        b_upd.click(update_profile, [uid, name, age, skin, clim, life, con, alg, oth], uid).then(load_user, uid, outs)
        b_add.click(add_product, [uid, p_name, p_brand, p_cat, p_open, p_pao, p_ing, p_qty, p_use, p_sto], inv); b_del.click(delete_product, [uid, del_id], inv)
        b_al.click(alerts_v2, uid, [al_html, pr_html, md_why])
        b_sk.click(scan_v2, [uid, img, sv], [o1, o2, o3, sc_html, sk_md, scan_state, cta])
        b_rt.click(routine_v2, [uid, us, scan_state], r_outs)
        b_go.click(routine_v2, [uid, gr.State(True), scan_state], r_outs).then(lambda: gr.Tabs(selected="routine"), None, tabs)
        dash = [kpi, p1, p2, p3, p4, p5, tr_md]; b_db.click(dash_v2, uid, dash); b_demo.click(add_demo, uid, None).then(dash_v2, uid, dash)
    return demo, ({} if in_blocks else kw)
