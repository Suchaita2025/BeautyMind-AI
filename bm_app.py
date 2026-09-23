import os, inspect, numpy as np, pandas as pd, gradio as gr
from PIL import Image
from bm_config import P, get_conn
from bm_ml import CATS, STORAGES, CLIMATES
from bm_alerts import run_user
from bm_routine import build_routine, validate, save_routine
from bm_skin import analyze, save_scan
import bm_dash as D

SKIN = ["Oily", "Dry", "Combination", "Normal", "Sensitive"]
LIFESTYLES = ["Office (AC)", "Outdoor/active", "Student", "Frequent traveler", "Work-from-home"]
CONCERNS = ["Acne", "Pigmentation", "Redness", "Dryness", "Fine lines", "Dullness", "Oiliness"]
ALLERGENS = ["Fragrance", "Benzoyl Peroxide", "Salicylic Acid", "Retinol", "Sulfur"]
SEV_E = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🟢"}
PRI_E = {"High": "🔴 High", "Medium": "🟠 Medium", "Low": "🟢 Low", "Discard": "⚫ Discard"}

def q(sql, params=()):
    with get_conn() as c: return pd.read_sql(sql, c, params=params)
def user_row(uid):
    if uid is None: raise gr.Error("Enter a user ID.")
    d = q("SELECT * FROM users WHERE user_id=?", (int(uid),))
    if d.empty: raise gr.Error(f"User {int(uid)} not found. Use an ID from 1-400 or create a profile.")
    return d.iloc[0]
def need_products(uid):
    user_row(uid)
    if not int(q("SELECT COUNT(*) n FROM products WHERE user_id=?", (int(uid),)).n[0]): raise gr.Error("This user has no products yet. Add some in the Profile tab.")

# ---------- profile & inventory
def inventory(uid):
    return q("SELECT product_id AS ID, name AS Product, category AS Category, open_date AS Opened, expiry_date AS Label_expiry, pao_months AS PAO_months, "
             "qty_left_pct AS Left_pct, usage_per_week AS Uses_per_week, storage AS Storage FROM products WHERE user_id=? ORDER BY product_id", (int(uid),))

def profile_html(u):
    chips = lambda s, c: "".join(f'<span style="display:inline-block;margin:2px 4px 2px 0;padding:3px 10px;border-radius:999px;background:{c}1a;color:{c};font-size:12px">{x.strip()}</span>'
                                 for x in str(s).split(",") if x.strip())
    return (f'<div style="padding:16px 18px;border-radius:16px;border:1px solid #e5e7eb"><div style="font-size:20px;font-weight:700">{u["name"]} '
            f'<span style="font-weight:400;color:#6b7280;font-size:14px">· age {u["age"]} · {u["skin_type"]} skin</span></div>'
            f'<div style="margin-top:6px;color:#6b7280;font-size:13px">{u["climate"]} climate · {u["lifestyle"]}</div>'
            f'<div style="margin-top:8px"><b style="font-size:12px">Concerns</b> {chips(u["concerns"], "#6366f1")}</div>'
            f'<div><b style="font-size:12px">Allergies</b> {chips(u["allergies"], "#e11d48")}</div></div>')

def load_user(uid):
    u = user_row(uid); al = [x.strip() for x in str(u["allergies"]).split(",") if x.strip() and x.strip() != "None"]
    return (profile_html(u), inventory(uid), u["name"], int(u["age"]), u["skin_type"], u["climate"], u["lifestyle"],
            [c for c in CONCERNS if c in str(u["concerns"])], [a for a in ALLERGENS if a in al], ", ".join(a for a in al if a not in ALLERGENS))

def _vals(name, age, skin, clim, life, con, alg, oth):
    al = list(alg) + [x.strip() for x in str(oth or "").split(",") if x.strip()]
    return ((name or "New user").strip(), int(age), skin, ", ".join(al) or "None", clim, life, ", ".join(con) or "None")

def create_profile(name, age, skin, clim, life, con, alg, oth):
    with get_conn() as c:
        uid = c.execute("INSERT INTO users(name,age,skin_type,allergies,climate,lifestyle,concerns) VALUES(?,?,?,?,?,?,?)", _vals(name, age, skin, clim, life, con, alg, oth)).lastrowid
    gr.Info(f"Created user {uid}. Add products next."); return uid

def update_profile(uid, name, age, skin, clim, life, con, alg, oth):
    user_row(uid)
    with get_conn() as c: c.execute("UPDATE users SET name=?,age=?,skin_type=?,allergies=?,climate=?,lifestyle=?,concerns=? WHERE user_id=?", (*_vals(name, age, skin, clim, life, con, alg, oth), int(uid)))
    gr.Info("Profile updated."); return uid

def add_product(uid, name, brand, cat, open_date, pao, ing, qty, use, storage):
    user_row(uid)
    if not (name or "").strip() or not (ing or "").strip(): raise gr.Error("Product name and ingredients are required.")
    try: od = pd.Timestamp(open_date)
    except Exception: raise gr.Error("Open date must look like 2026-08-15.")
    exp = (od + pd.DateOffset(months=int(pao))).strftime("%Y-%m-%d")
    with get_conn() as c:
        c.execute("INSERT INTO products(user_id,name,brand,category,open_date,expiry_date,pao_months,ingredients,qty_left_pct,usage_per_week,storage) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (int(uid), name.strip(), (brand or "").strip(), cat, od.strftime("%Y-%m-%d"), exp, int(pao), ing.strip(), float(qty), float(use), storage))
    gr.Info("Product added."); return inventory(uid)

def delete_product(uid, pid):
    user_row(uid)
    with get_conn() as c: c.execute("DELETE FROM products WHERE product_id=? AND user_id=?", (int(pid or 0), int(uid)))
    return inventory(uid)

# ---------- alerts & priority
def run_inventory(uid):
    need_products(uid); rk, al = run_user(int(uid), explain_high=True, save=True); names = rk.set_index("product_id")["name"]
    A = pd.DataFrame({"": al.severity.map(SEV_E), "Severity": al.severity, "Type": al.alert_type, "Product": al.product_id.map(names), "Message": al.message})
    R = pd.DataFrame({"Priority": rk.priority.map(PRI_E), "Product": rk["name"], "Category": rk.category, "Days left": rk.days_left.astype(int),
                      "Confidence %": rk.confidence.astype(int), "Model risk": rk.risk, "Waste %": rk.waste_pct.astype(int), "Reason": rk.reason})
    why = "\n".join(f"- **{r['name']}**: {r['why_ml']}" for _, r in rk[rk.priority == "High"].iterrows() if r["why_ml"]) or "_No High-priority products._"
    return A, R, why

# ---------- skin analysis
def score_html(res):
    def bar(label, v, hb):
        good = v if hb else 100 - v; col = "#10b981" if good >= 67 else "#f59e0b" if good >= 34 else "#e11d48"
        return (f'<div style="margin:8px 0"><div style="display:flex;justify-content:space-between;font-size:13px"><span>{label}</span><b>{v:.0f}/100</b></div>'
                f'<div style="height:9px;border-radius:99px;background:#e5e7eb"><div style="width:{v:.0f}%;height:9px;border-radius:99px;background:{col}"></div></div></div>')
    return ('<div style="padding:16px;border-radius:16px;border:1px solid #e5e7eb"><div style="font-size:13px;color:#6b7280">Skin type</div>'
            f'<div style="font-size:22px;font-weight:700">{res["skin_type"]} <span style="font-size:13px;font-weight:400;color:#6b7280">({res["type_conf"]:.0%} CNN confidence)</span></div>'
            + bar("Acne (lower is better)", res["acne"], False) + bar("Pigmentation (lower is better)", res["pigmentation"], False)
            + bar("Redness (lower is better)", res["redness"], False) + bar("Hydration (higher is better)", res["hydration"], True)
            + bar("Overall skin score", res["overall"], True)
            + f'<div style="font-size:11px;color:#9ca3af;margin-top:6px">Face detection: {res["face_method"]}</div></div>')

def do_scan(uid, img, save):
    user_row(uid)
    if img is None: raise gr.Error("Upload or capture a face photo first.")
    try: res = analyze(img)
    except Exception as e: raise gr.Error(f"Skin analysis failed: {e}")
    if "no face" in res["face_method"]: gr.Warning("No face detected: the whole image was used, so results are unreliable.")
    if save: save_scan(int(uid), res, img)
    md = ("**Why these results**\n" + "\n".join("- " + w for w in res["why"])
          + "\n\n_Cosmetic guidance only, not a medical diagnosis. Skin type and acne come from CNNs trained on small public datasets; pigmentation, redness and hydration are heuristic image-analysis estimates._"
          + ("\n\n✅ Saved to your scan history." if save else ""))
    return res["imgs"]["face"], res["imgs"]["gc_type"], res["imgs"]["gc_acne"], score_html(res), md

# ---------- routine
def do_routine(uid, use_scan):
    need_products(uid); R = build_routine(int(uid), use_scan=use_scan); v = validate(R, R["user"]["allergies"]); save_routine(int(uid), R)
    def steps(slot):
        return pd.DataFrame([dict(Step=n, Category=i["category"], Product=i["name"], When=i["days"], Why=i["reason"]) for n, i in enumerate([x for x in R["items"] if x["slot"] == slot], 1)],
                            columns=["Step", "Category", "Product", "When", "Why"])
    ok = "✅ Safety check passed: no expired or allergen products and no High/Medium ingredient clashes in the same slot." if not v else "⚠️ Check failed: " + "; ".join(v[:3])
    ex = pd.DataFrame(R["excluded"], columns=["name", "kind", "reason"]) if R["excluded"] else pd.DataFrame(columns=["name", "kind", "reason"])
    return (R["summary"] + "\n\n" + ok, steps("AM"), steps("PM"), R["grid"].reset_index().rename(columns={"index": "Day"}), ex,
            "\n".join("- " + n for n in R["notes"]) or "_No notes._")

# ---------- dashboard
def do_dash(uid):
    need_products(uid); rk, al = run_user(int(uid), explain_high=False, save=True); sc = D.get_scans(uid)
    return D.kpi_html(rk, al, uid), D.fig_status(rk), D.fig_days(rk), D.fig_waste(rk), D.fig_alerts(al), D.fig_trend(sc), D.trend_md(sc)
def add_demo(uid): user_row(uid); D.seed_demo_scans(uid); gr.Info("Added 8 SYNTHETIC weekly scans (demo only).")

HERO = ('<div style="padding:22px 26px;border-radius:20px;background:linear-gradient(135deg,#f43f5e,#8b5cf6);color:white">'
        '<div style="font-size:28px;font-weight:800">✨ BeautyMind AI</div>'
        '<div style="opacity:.92;margin-top:4px">Explainable decision support for cosmetic expiry management and personalised skincare routines</div></div>')
CSS = ".gradio-container{max-width:1180px !important;margin:0 auto !important} footer{display:none !important}"

def build_app():
    theme = gr.themes.Soft(primary_hue="rose", secondary_hue="indigo", neutral_hue="slate", font=[gr.themes.GoogleFont("Inter"), "sans-serif"])
    kw = dict(theme=theme, css=CSS); in_blocks = "theme" in inspect.signature(gr.Blocks.__init__).parameters   # Gradio 6 moved theme/css to launch()
    with gr.Blocks(title="BeautyMind AI", **(kw if in_blocks else {})) as demo:
        gr.HTML(HERO)
        with gr.Row(equal_height=True):
            uid = gr.Number(value=1, precision=0, label="User ID (1-400 are demo users)", scale=1); load = gr.Button("Load user", variant="primary", scale=1)
        with gr.Tabs():
            with gr.Tab("👤 Profile & Inventory"):
                prof = gr.HTML(); inv = gr.Dataframe(label="My cosmetics", interactive=False, wrap=True)
                with gr.Accordion("Create or edit profile", open=False):
                    with gr.Row(): name = gr.Textbox(label="Name"); age = gr.Slider(16, 80, value=28, step=1, label="Age")
                    with gr.Row():
                        skin = gr.Dropdown(SKIN, value="Combination", label="Skin type"); clim = gr.Dropdown(CLIMATES, value="Humid", label="Climate")
                        life = gr.Dropdown(LIFESTYLES, value=LIFESTYLES[0], label="Lifestyle")
                    con = gr.CheckboxGroup(CONCERNS, label="Concerns"); alg = gr.CheckboxGroup(ALLERGENS, label="Allergies")
                    oth = gr.Textbox(label="Other allergens (comma-separated ingredient names)")
                    with gr.Row(): b_new = gr.Button("Create new profile"); b_upd = gr.Button("Update this profile")
                with gr.Accordion("Add or remove a product", open=False):
                    with gr.Row(): p_name = gr.Textbox(label="Product name"); p_brand = gr.Textbox(label="Brand"); p_cat = gr.Dropdown(CATS, value="Serum", label="Category")
                    p_ing = gr.Textbox(label="Ingredients (comma-separated, e.g. Water, Glycerin, Retinol, Phenoxyethanol)", lines=2)
                    with gr.Row():
                        p_open = gr.Textbox(value=pd.Timestamp.today().strftime("%Y-%m-%d"), label="Open date (YYYY-MM-DD)"); p_pao = gr.Slider(3, 36, value=12, step=1, label="PAO (months)")
                        p_sto = gr.Dropdown(STORAGES, value="Drawer", label="Storage")
                    with gr.Row(): p_qty = gr.Slider(0, 100, value=100, label="Amount left %"); p_use = gr.Slider(0, 14, value=7, step=.5, label="Uses per week")
                    b_add = gr.Button("Add product", variant="primary")
                    with gr.Row(): del_id = gr.Number(label="Product ID to remove", precision=0); b_del = gr.Button("Remove product")
            with gr.Tab("🔔 Alerts & Priority"):
                b_al = gr.Button("Analyze my inventory", variant="primary")
                gr.Markdown("**Smart alerts:** expiry tiers, waste risk, unused, duplicates, routine conflicts"); t_al = gr.Dataframe(interactive=False, wrap=True)
                gr.Markdown("**Product priority ranking** with reasons"); t_pr = gr.Dataframe(interactive=False, wrap=True)
                gr.Markdown("**Why the model thinks so:** SHAP drivers for High-priority products"); md_why = gr.Markdown()
                with gr.Accordion("Global SHAP: what drives shelf-life predictions", open=False), gr.Row():
                    for f in ("shap_summary", "shap_bar"):
                        fp = f"{P['outputs']}/{f}.png"
                        if os.path.exists(fp): gr.Image(value=np.asarray(Image.open(fp).convert("RGB")), interactive=False, show_label=False)
            with gr.Tab("📸 Skin Analysis"):
                with gr.Row():
                    with gr.Column(scale=1):
                        img = gr.Image(label="Face photo (front-facing, good light)", type="numpy", sources=["upload", "webcam"])
                        sv = gr.Checkbox(True, label="Save this scan to my history"); b_sk = gr.Button("Analyze skin", variant="primary"); sc_html = gr.HTML()
                    with gr.Column(scale=2):
                        with gr.Row(): o1 = gr.Image(label="Skin region used"); o2 = gr.Image(label="Grad-CAM: skin type"); o3 = gr.Image(label="Grad-CAM: acne")
                        sk_md = gr.Markdown()
            with gr.Tab("🧴 Routine"):
                with gr.Row(): us = gr.Checkbox(True, label="Use my latest skin scan"); b_rt = gr.Button("Generate my routine", variant="primary")
                rt_md = gr.Markdown(); gr.Markdown("#### ☀️ Morning"); t_am = gr.Dataframe(interactive=False, wrap=True)
                gr.Markdown("#### 🌙 Evening"); t_pm = gr.Dataframe(interactive=False, wrap=True)
                gr.Markdown("#### 📅 Weekly plan"); t_gr = gr.Dataframe(interactive=False, wrap=True)
                gr.Markdown("#### Not used, and why"); t_ex = gr.Dataframe(interactive=False, wrap=True); gr.Markdown("#### Notes"); rt_notes = gr.Markdown()
            with gr.Tab("📊 Dashboard"):
                with gr.Row(): b_db = gr.Button("Refresh dashboard", variant="primary"); b_demo = gr.Button("Add demo skin history (synthetic)")
                kpi = gr.HTML()
                with gr.Row(): p1 = gr.Plot(); p2 = gr.Plot()
                with gr.Row(): p3 = gr.Plot(); p4 = gr.Plot()
                p5 = gr.Plot(); tr_md = gr.Markdown()
        gr.Markdown("_Shelf-life data is synthetic. Skin scores are cosmetic guidance, not medical advice. Routine rules are editable heuristics._")
        outs = [prof, inv, name, age, skin, clim, life, con, alg, oth]
        load.click(load_user, uid, outs); demo.load(load_user, uid, outs)
        b_new.click(create_profile, [name, age, skin, clim, life, con, alg, oth], uid).then(load_user, uid, outs)
        b_upd.click(update_profile, [uid, name, age, skin, clim, life, con, alg, oth], uid).then(load_user, uid, outs)
        b_add.click(add_product, [uid, p_name, p_brand, p_cat, p_open, p_pao, p_ing, p_qty, p_use, p_sto], inv); b_del.click(delete_product, [uid, del_id], inv)
        b_al.click(run_inventory, uid, [t_al, t_pr, md_why]); b_sk.click(do_scan, [uid, img, sv], [o1, o2, o3, sc_html, sk_md])
        b_rt.click(do_routine, [uid, us], [rt_md, t_am, t_pm, t_gr, t_ex, rt_notes])
        dash = [kpi, p1, p2, p3, p4, p5, tr_md]; b_db.click(do_dash, uid, dash); b_demo.click(add_demo, uid, None).then(do_dash, uid, dash)
    return demo, ({} if in_blocks else kw)