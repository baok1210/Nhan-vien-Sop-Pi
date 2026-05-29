"""FastAPI WebUI - Dashboard, Config, Crawl, Products"""
import json, os, threading, time
from pathlib import Path
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from src.main import load_config, validate_config
from src.source.ali1688 import Ali1688Scraper
from src.source.aliexpress_api import AliExpressAPI

BASE = Path(__file__).resolve().parent
TEMPLATES = BASE / "templates"
CONFIG_PATH = Path("config/config.json")
DATA_DIR = Path("data/raw")

app = FastAPI(title="China Dropship to Shopee")
env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
crawl_status = {"running": False, "products": 0, "log": []}


def _render(name: str, **kw) -> str:
    t = env.get_template(name)
    return t.render(**kw)


def _log(msg: str):
    crawl_status["log"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    cfg = load_config()
    warnings = validate_config(cfg)
    products = []
    if DATA_DIR.exists():
        for f in DATA_DIR.glob("*.json"):
            try:
                products.extend(json.loads(f.read_text("utf-8")))
            except Exception:
                pass
    return _render("index.html", current="/", config=cfg, warnings=warnings,
                   products_count=len(products), crawl_status=crawl_status)


@app.get("/config", response_class=HTMLResponse)
def config_page(request: Request):
    cfg = load_config()
    params = dict(request.query_params)
    return _render("config.html", current="/config", ok=params.get("ok"),
                   err=params.get("err"),
                   config_json=json.dumps(cfg, ensure_ascii=False, indent=2))


@app.post("/config")
def config_save(config_json: str = Form(...)):
    try:
        data = json.loads(config_json)
        CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return RedirectResponse("/config?ok=1", status_code=303)
    except json.JSONDecodeError:
        return RedirectResponse("/config?err=1", status_code=303)


@app.get("/crawl", response_class=HTMLResponse)
def crawl_page(request: Request):
    cfg = load_config()
    return _render("crawl.html", current="/crawl", config=cfg, crawl_status=crawl_status)


@app.post("/crawl/start")
def crawl_start():
    if crawl_status["running"]:
        return {"ok": False, "msg": "Dang chay roi"}
    crawl_status["running"] = True
    crawl_status["products"] = 0
    crawl_status["log"] = []
    threading.Thread(target=_run_crawl, daemon=True).start()
    return {"ok": True}


@app.get("/crawl/status")
def crawl_get_status():
    return crawl_status


def _run_crawl():
    cfg = load_config()
    all_products = []
    src_1688 = cfg.get("source", {}).get("1688", {})
    if src_1688.get("enabled", True):
        for kw in cfg.get("niche", {}).get("keywords_cn", []):
            _log(f"1688: dang crawl '{kw}'...")
            scraper = Ali1688Scraper(src_1688)
            try:
                products = scraper.crawl_by_keywords([kw])
                all_products.extend(products)
                _log(f"1688: {len(products)} san pham tu '{kw}'")
            finally:
                scraper.close()
    src_ae = cfg.get("source", {}).get("aliexpress", {})
    if src_ae.get("enabled", True):
        if src_ae.get("app_key") and src_ae.get("app_secret"):
            api = AliExpressAPI(src_ae["app_key"], src_ae["app_secret"])
            for kw in cfg.get("niche", {}).get("keywords_en", []):
                _log(f"AliExpress API: dang tim '{kw}'...")
                products = api.crawl_by_keywords([kw])
                all_products.extend(products)
                _log(f"AliExpress API: {len(products)} san pham")
        else:
            _log("AliExpress: bo qua (can API key)")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for p in all_products:
        out.append({"id": p.id, "title_cn": p.title_cn, "price_cny": p.price_cny, "image_urls": p.image_urls[:3], "platform": p.platform, "supplier_name": p.supplier_name, "sales_count": p.sales_count})
    (DATA_DIR / "products.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(f"Hoan tat! Tong: {len(out)} san pham")
    crawl_status["products"] = len(out)
    crawl_status["running"] = False


@app.get("/products", response_class=HTMLResponse)
def products_page(request: Request):
    products = []
    f = DATA_DIR / "products.json"
    if f.exists():
        try:
            products = json.loads(f.read_text("utf-8"))
        except Exception:
            pass
    return _render("products.html", current="/products", products=products)
