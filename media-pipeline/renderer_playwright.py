#!/usr/bin/env python3
# media-pipeline/renderer_playwright.py
# Render HTML+CSS to PNG via Playwright + Chromium (RTL + Google Fonts)

import os
import base64
import argparse

from playwright.sync_api import sync_playwright


def render_png(html: str, out_path: str, width: int, height: int, wait_ms: int = 3000):
	os.makedirs(os.path.dirname(out_path), exist_ok=True)
	with sync_playwright() as p:
		browser = p.chromium.launch()
		page = browser.new_page(viewport={"width": width, "height": height, "deviceScaleFactor": 1})
		page.set_content(html, wait_until="load")
		page.wait_for_timeout(wait_ms)
		page.screenshot(path=out_path, full_page=False, type="png")
		browser.close()


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("--html", required=True, help="Path to HTML file")
	ap.add_argument("--out", required=True, help="Output PNG path")
	ap.add_argument("--width", type=int, required=True)
	ap.add_argument("--height", type=int, required=True)
	ap.add_argument("--wait_ms", type=int, default=3000)
	args = ap.parse_args()

	with open(args.html, "r", encoding="utf-8") as f:
		html = f.read()

	render_png(html, args.out, args.width, args.height, args.wait_ms)


if __name__ == "__main__":
	main()
