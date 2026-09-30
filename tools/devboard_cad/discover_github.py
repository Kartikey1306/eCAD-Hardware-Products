"""Enumerate manufacturer board repositories and turn them into records (issue #28).

Issue #28 section 9 is the hard part of the issue: a family name is not a product, and a
useful database expands every family into its actual boards. Doing that by hand across the
31 ecosystems in section 2 does not finish, so this walks the manufacturers' own GitHub
organisations, matches repositories to the families the issue names, confirms from the
repository tree that design files are actually present, and derives what identity it can
from the manufacturer's own README.

The discipline from verify.py carries over unchanged. This tool decides nothing about
availability: it proposes candidate URLs from a pinned tree and marks formats the tree
proves absent. Identity it cannot extract is left UNVERIFIED rather than guessed, which
holds the record at 'partial' and makes the gap visible instead of plausible.

Coverage grows by editing vendors.json, not this file.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devboard_cad.harvest_github import (  # noqa: E402
    ABSENCE_CLAIMABLE,
    _gh_api,
    build_record,
    classify_paths,
)

HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parents[2]
VENDORS = HERE.parent / "vendors.json"

# A repository is only a candidate if its name or description suggests design files rather
# than firmware, a driver port or a library. The tree check that follows is authoritative;
# this only keeps the number of tree calls sane.
HW_HINT = re.compile(r"(pcb|hardware|-hw\b|_hw\b|schematic|eagle|kicad|altium|oshw|board)",
                     re.I)

# Part numbers, in each manufacturer's own notation, as their READMEs write them.
PART_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (r"adafruit\.com/products?/(\d{3,5})", r"\1"),
    (r"\b(DEV|SEN|BOB|WRL|LCD|COM|KIT|TOL)-(\d{4,5})\b", r"\1-\2"),
    (r"sparkfun\.com/products/(\d{4,5})", r"\1"),
    (r"seeedstudio\.com/[A-Za-z0-9\-]*?-p-(\d{3,5})", r"\1"),
)

# MCU/SoC families, longest first so 'ESP32-S3' is not truncated to 'ESP32'.
MCU_PATTERNS: Tuple[str, ...] = (
    r"RP2350[AB]?", r"RP2040",
    # Parts the manufacturers name in their own README but that the first pass missed.
    r"ATSAMD51[A-Z0-9]*", r"SAMD51[A-Z0-9]*", r"ATSAMD21[A-Z0-9]*",
    r"ATmega32[Uu]4", r"(?<![A-Za-z0-9])32[Uu]4(?![A-Za-z0-9])",
    r"TDA4VM", r"AM572[0-9]", r"AM67[A-Z]?", r"AM62[0-9A-Z]*", r"AM335[0-9]",
    r"OSD335[0-9][A-Z-]*", r"CC13[0-9]{2}[A-Z0-9]*", r"CC26[0-9]{2}[A-Z0-9]*",
    r"TH1520", r"MPFS[0-9]+[A-Z]*", r"PolarFire\s?SoC",
    r"i\.?MX\s?RT10[0-9]{2}", r"(?:FE|Freedom\s+E)310[A-Z0-9-]*", r"ICE40[A-Z0-9]*",
    r"MAX3262[0-9]", r"nRF5182[0-9]",
    r"ESP32-(?:S2|S3|C2|C3|C5|C6|H2|P4)", r"ESP32", r"ESP8266",
    r"nRF5340", r"nRF52840", r"nRF52832", r"nRF9160", r"nRF7002",
    r"SAMD51", r"SAMD21", r"SAME5[0-9]", r"ATSAMD[0-9]+[A-Z0-9]*",
    r"STM32[A-Z][0-9]{3}[A-Z0-9]*", r"STM32[A-Z][0-9]",
    r"ATmega\d+[A-Z0-9]*", r"ATtiny\d+[A-Z0-9]*", r"ATSAMD\d+",
    r"AM335[0-9]", r"AM62[0-9A-Z]*", r"OSD335[0-9]-?[A-Z]*",
    r"RK3588[A-Z]?", r"RK3568", r"RK3399", r"RK3566",
    r"i\.MX\s?8[A-Z0-9]*", r"i\.MX\s?RT\d+",
    r"Zynq\s?UltraScale\+?", r"Zynq-?7000", r"Artix-?7", r"Spartan-?7", r"Kintex-?7",
    r"K210", r"BL[0-9]{3}", r"CH32V\d+", r"GD32[A-Z0-9]+",
    r"nRF54[A-Z0-9]*", r"MAX32625", r"Apollo3",
)
ARCH_BY_MCU: Tuple[Tuple[str, str], ...] = (
    (r"RP2350", "Arm Cortex-M33 / RISC-V Hazard3 (dual)"),
    (r"TDA4VM|AM67|AM62", "Arm Cortex-A53"),
    (r"AM572", "Arm Cortex-A15"),
    (r"TH1520", "RISC-V RV64GC"),
    (r"MPFS|PolarFire", "RISC-V RV64GC"),
    (r"FE310", "RISC-V RV32IMAC"),
    (r"ICE40", "FPGA (no CPU core)"),
    (r"i\.?MX\s?RT10", "Arm Cortex-M7"),
    (r"CC13|CC26", "Arm Cortex-M4F"),
    (r"ATSAMD51|SAMD51", "Arm Cortex-M4F"),
    (r"ATSAMD21", "Arm Cortex-M0+"),
    (r"32[Uu]4", "AVR"),
    (r"RP2040", "Dual Arm Cortex-M0+"),
    (r"ESP32-(S2|S3)", "Xtensa LX7"),
    (r"ESP32-(C2|C3|C5|C6|H2)", "RISC-V RV32IMC"),
    (r"ESP32-P4", "RISC-V RV32"),
    (r"ESP32", "Xtensa LX6"),
    (r"ESP8266", "Xtensa L106"),
    (r"nRF5340", "Arm Cortex-M33 (dual)"),
    (r"nRF52|nRF9160|nRF7002", "Arm Cortex-M4F"),
    (r"SAMD51|SAME5", "Arm Cortex-M4F"),
    (r"SAMD21|ATSAMD21", "Arm Cortex-M0+"),
    (r"STM32", "Arm Cortex-M"),
    (r"ATmega|ATtiny", "AVR"),
    (r"AM335|OSD335", "Arm Cortex-A8"),
    (r"AM62", "Arm Cortex-A53"),
    (r"RK35", "Arm Cortex-A"),
    (r"K210", "RISC-V RV64GC"),
    (r"Apollo3", "Arm Cortex-M4F"),
)
# Add-on boards -- FeatherWings, shields, HATs, capes, Qwiic breakouts -- are in scope per
# issue #28 section 2.20, but most carry no MCU. Recording "UNVERIFIED" for them would
# describe a gap in this database rather than the board, so they get their own sentinel.
# Matched against the PRODUCT NAME only, never the description. A description that happens
# to mention a connector or an enclosure ("an Arduino Uno compatible board with a USB-C
# connector") says nothing about whether the board carries a processor, and treating it as
# though it did put "not-applicable" on real MCU boards.
ADDON = re.compile(
    r"(wing\b|shield|\bhat\b|\bcape[sd]?\b|bonnet|breakout|doubler|tripler|"
    r"\bquad\b|proto\b|terminal block|stacking|header|"
    # Product lines that are add-ons by definition of what the line is.
    r"\bgizmo\b|\bbff\b|add[- ]on|carrier|notecarrier|function board|"
    r"\badapter\b|\bpack\b|update tool|light pipe)", re.I)

# Phrases with which a vendor *classifies* the product, as opposed to words that merely
# appear in prose about it. Only these are trusted from a description; the generic ADDON
# words are matched against the product name alone.
ADDON_CLASS = re.compile(
    r"(breakout board|carrier board|function board|add[- ]on board|daughter ?board|"
    r"\bshield\b|\bHAT for\b|\bcape for\b|featherwing|qwiic[- ]enabled breakout|"
    r"expansion board|adapter board|\bbonnet\b)", re.I)


def is_addon(product_name: str, description: str = "") -> bool:
    """True when the product line carries no processor by definition of what the line is.

    Separators are normalised first: `\\b` does not fire between "_" and "G", so
    "Adafruit_TFT_Gizmo" would otherwise never match \\bgizmo\\b.

    The description is only consulted for phrases that classify the product. Matching
    generic words there put "not-applicable" on 22 real MCU boards, because "an Arduino
    Uno compatible board with a USB-C connector" mentions a connector without being one.
    """
    if ADDON.search(re.sub(r"[-_]+", " ", product_name)):
        return True
    return bool(description and ADDON_CLASS.search(description))


NOISE = re.compile(r"[-_]+(pcb|hardware|hw|files?|design|eagle|kicad|altium|board)$", re.I)


def _load_vendors() -> List[Dict[str, Any]]:
    return json.loads(VENDORS.read_text(encoding="utf-8"))["vendors"]


def _readme(repo: str) -> str:
    try:
        payload = _gh_api(f"repos/{repo}/readme")
        return base64.b64decode(payload.get("content", "")).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 - a missing or unreadable README is not fatal
        return ""


def match_family(name: str, description: str, families: Sequence[str]) -> Optional[str]:
    blob = f"{name} {description}".lower().replace("_", " ").replace("-", " ")
    best: Optional[str] = None
    for family in families:
        needle = family.lower().replace("_", " ").replace("-", " ")
        if re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", blob):
            if best is None or len(family) > len(best):
                best = family
    return best


def extract_part_number(text: str) -> Optional[str]:
    for pattern, replacement in PART_PATTERNS:
        found = re.search(pattern, text, re.I)
        if found:
            return found.expand(replacement)
    return None


# Part numbers are conventionally upper-case, but a few carry their own spelling.
_MCU_SPELLING = (
    (r"^I\.?MX\s?RT", "i.MX RT"),
    (r"^I\.?MX", "i.MX "),
    (r"^FREEDOM\s+E310", "SiFive FE310"),
)


def extract_mcu(*texts: str) -> Optional[str]:
    blob = " ".join(texts)
    for pattern in MCU_PATTERNS:
        found = re.search(pattern, blob, re.I)
        if found:
            part = re.sub(r"\s+", " ", found.group(0).upper()).strip()
            for spelling, replacement in _MCU_SPELLING:
                if re.match(spelling, part):
                    return re.sub(spelling, replacement, part, count=1).replace("  ", " ").strip()
            return part
    return None


def arch_for(mcu: Optional[str]) -> Optional[str]:
    if not mcu:
        return None
    for pattern, arch in ARCH_BY_MCU:
        if re.search(pattern, mcu, re.I):
            return arch
    return None


# Repository descriptions are written for humans browsing GitHub, not as product names.
# These prefixes wrap the product name and are stripped; the patterns below reject a
# description outright, because nothing usable can be recovered from it.
_DESC_PREFIX = re.compile(
    r"^\s*(?:(?:open[- ]?source|eagle ?cad|eagle|kicad|altium|pcb|hardware|design|"
    r"documentation|tutorial|schematics?|repo(?:sitory)?|files?|and)\s+)+"
    r"(?:for|of)\s+(?:the\s+)?", re.I)
_DESC_REJECT = re.compile(
    r"^\s*(mirror of|presented by|an? |the |tiny |dev board for|breakout board for|"
    r"qwiic enabled|micromod function board|https?://)", re.I)


def _prefix(name: str, manufacturer: str) -> str:
    """Prepend the manufacturer only when the name does not already carry it."""
    brand = manufacturer.split()[0]
    if brand.lower().rstrip(".") in name.lower().replace(".", ""):
        return re.sub(r"\s+", " ", name).strip()
    return re.sub(r"\s+", " ", f"{brand} {name}").strip()


def board_name(repo_name: str, description: str, manufacturer: str) -> str:
    """Prefer the manufacturer's own description; fall back to a de-slugged repo name.

    A description is only usable when it names the product. "Mirror of https://openbeagle"
    and "An mbed os enabled board based on the Artemis module" do not, so they are rejected
    in favour of the repository name, which always encodes the board.
    """
    head = (description or "").split(". ")[0].split(" - ")[0].strip()
    # A description often continues into a relative clause or pairs two products.
    # Everything after these joins describes rather than names.
    head = re.split(r",\s+(?:which|that|a\b)|\s+and the\s+|\s+\(?aka\b",
                    head, maxsplit=1, flags=re.I)[0].strip()
    head = head.split(":")[0].strip() if 3 < len(head.split(":")[0]) < 60 else head
    for _ in range(2):                      # "Open source PCB files for the X"
        stripped = _DESC_PREFIX.sub("", head)
        if stripped == head:
            break
        head = stripped.strip()
    head = re.sub(r"\s*\(?(pcb|eagle ?cad|kicad|altium)( files?)?\)?\s*$", "", head, flags=re.I)
    head = head.strip(" .,-–—")
    if (3 < len(head) < 70 and "http" not in head.lower()
            and not _DESC_REJECT.match(head)):
        return re.sub(r"\s+", " ", head)

    slug = NOISE.sub("", repo_name)
    slug = re.sub(r"^(oshw|hardware)[-_]+", "", slug, flags=re.I)
    slug = slug.replace("_", " ").replace("-", " ").strip()
    slug = " ".join(_recase(w, i == 0) for i, w in enumerate(slug.split()))
    return _prefix(slug, manufacturer)


# Repository names are lowercase slugs, so a de-slugged fallback reads as prose unless the
# tokens that are acronyms or part numbers are put back into their conventional case.
_ACRONYMS = {
    "ai", "io", "hat", "usb", "rf", "rfm", "adc", "dac", "imu", "gps", "gnss", "led",
    "sd", "spi", "i2c", "uart", "pcb", "fpga", "arm", "oled", "lcd", "tft", "can",
    "ble", "nfc", "lte", "poe", "hdmi", "mcu", "soc",
}
# Words whose conventional casing is neither lower, Title nor UPPER.
_MIXED = {"iot": "IoT", "wifi": "WiFi", "featherwing": "FeatherWing",
          "itsybitsy": "ItsyBitsy", "redboard": "RedBoard", "micromod": "MicroMod",
          "beaglebone": "BeagleBone", "beagleplay": "BeaglePlay", "beaglev": "BeagleV",
          "beagley": "BeagleY", "pocketbeagle": "PocketBeagle", "sparkfun": "SparkFun",
          "beagleconnect": "BeagleConnect", "macropad": "MacroPad", "qwiic": "Qwiic"}
# Joining words stay lowercase unless they lead the name.
_MINOR = {"for", "to", "and", "with", "of", "the", "a", "in", "on"}


def _recase(word: str, first: bool = False) -> str:
    low = word.lower()
    if low in _MIXED:
        return _MIXED[low]
    if low in _ACRONYMS:
        return low.upper()
    if low in _MINOR and not first:
        return low
    if any(ch.isdigit() for ch in low):     # rp2040, esp32, samd21e, f9p
        return low.upper()
    return word[:1].upper() + word[1:] if word.islower() else word


def board_id(org: str, repo_name: str) -> str:
    slug = NOISE.sub("", repo_name).lower()
    slug = re.sub(rf"^{re.escape(org.lower())}[-_]+", "", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return f"{org.lower()}:{slug or repo_name.lower()}"


def org_repos(org: str) -> List[Dict[str, Any]]:
    repos: List[Dict[str, Any]] = []
    page = 1
    while True:
        batch = _gh_api(f"orgs/{org}/repos?per_page=100&type=public&page={page}")
        if not isinstance(batch, list) or not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def discover(vendor: Dict[str, Any], limit: Optional[int] = None,
             verbose: bool = True) -> List[Dict[str, Any]]:
    org = vendor["org"]
    found: List[Dict[str, Any]] = []
    for repo in org_repos(org):
        if repo.get("fork") or repo.get("archived"):
            continue
        name, description = repo["name"], repo.get("description") or ""
        family = match_family(name, description, vendor["families"])
        if not family:
            continue
        if not (HW_HINT.search(name) or HW_HINT.search(description)):
            continue
        found.append({"repo": repo["full_name"], "name": name, "description": description,
                      "family": family, "default_branch": repo.get("default_branch"),
                      "license": (repo.get("license") or {}).get("spdx_id"),
                      "html_url": repo.get("html_url")})
        if limit and len(found) >= limit:
            break
    if verbose:
        print(f"  {org}: {len(found)} candidate repositories")
    return found


def _tree(repo: str, ref: Optional[str]) -> Tuple[Optional[str], List[str], bool]:
    commit = _gh_api(f"repos/{repo}/commits/{ref or 'HEAD'}")
    sha = commit["sha"]
    tree = _gh_api(f"repos/{repo}/git/trees/{sha}?recursive=1")
    paths = [i["path"] for i in tree.get("tree", []) if i.get("type") == "blob"]
    return sha, paths, bool(tree.get("truncated"))


def build(entry: Dict[str, Any], vendor: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return a record for one repository, or None when it holds no design files."""
    sha, paths, truncated = _tree(entry["repo"], entry.get("default_branch"))
    if truncated:
        return None  # absence is unprovable against a partial listing
    found = classify_paths(paths)
    if not any(f in found for f in ABSENCE_CLAIMABLE):
        return None  # matched by name, but holds no design files

    readme = _readme(entry["repo"])
    part = extract_part_number(readme) or extract_part_number(entry["description"] or "")
    mcu = extract_mcu(entry["name"], entry["description"] or "", readme[:4000])
    product_page = vendor["product_page"]
    if "{part_number}" in product_page:
        product_page = (product_page.replace("{part_number}", part) if part
                        else product_page.split("{")[0])
    identity = {
        "manufacturer": vendor["manufacturer"],
        "family": entry["family"],
        "board": board_name(entry["name"], entry["description"] or "",
                            vendor["manufacturer"]),
        "part_number": part or "UNVERIFIED",
        "revision": "unverified",
        "mcu_soc": mcu or ("not-applicable"
                           if is_addon(entry["name"], entry["description"] or "")
                           else "UNVERIFIED"),
        "cpu_architecture": arch_for(mcu),
        "product_status": "unknown",
        "official_product_page": product_page,
        "official_documentation": None,
    }
    meta = {"license": {"spdx_id": entry.get("license")}, "html_url": entry["html_url"]}
    return build_record(board_id(vendor["org"], entry["name"]), entry["repo"], sha, meta,
                        found, identity)


def cmd_discover(args: argparse.Namespace) -> int:
    vendors = [v for v in _load_vendors()
               if not args.org or v["org"].lower() in {o.lower() for o in args.org}]
    manifest: List[Dict[str, Any]] = []
    for vendor in vendors:
        for entry in discover(vendor, limit=args.limit):
            entry["vendor"] = vendor["org"]
            manifest.append(entry)
    Path(args.out).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"{len(manifest)} candidate repositories -> {args.out}")
    return 0


def cmd_emit(args: argparse.Namespace) -> int:
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    vendors = {v["org"]: v for v in _load_vendors()}
    out_dir = Path(args.root) / "tools" / "devboard_cad" / "records"
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = {json.loads(p.read_text(encoding="utf-8"))["board_id"]: p
                for p in out_dir.glob("*.json")}
    written = skipped = empty = 0
    for entry in manifest[args.start:args.start + args.count if args.count else None]:
        vendor = vendors[entry["vendor"]]
        bid = board_id(vendor["org"], entry["name"])
        if bid in existing and not args.overwrite:
            skipped += 1
            continue
        try:
            record = build(entry, vendor)
        except Exception as exc:  # noqa: BLE001 - one bad repo must not stop the run
            print(f"  ! {entry['repo']}: {exc}")
            continue
        if record is None:
            empty += 1
            continue
        path = out_dir / (record["board_id"].replace(":", "__") + ".json")
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(record, handle, indent=2)
            handle.write("\n")
        written += 1
        if args.verbose:
            candidates = sum(1 for e in record["files"].values() if e["url"])
            print(f"  {record['board_id']:44} {candidates:2} candidate(s)  "
                  f"{record['mcu_soc']}")
    print(f"\nwritten={written} skipped_existing={skipped} no_design_files={empty}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="discover_github.py",
                                     description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(REPO_ROOT))
    sub = parser.add_subparsers(dest="command", required=True)

    d = sub.add_parser("discover", help="list candidate manufacturer repositories")
    d.add_argument("--org", action="append", help="restrict to this org (repeatable)")
    d.add_argument("--limit", type=int, default=None, help="cap candidates per org")
    d.add_argument("--out", default="devboard-cad-candidates.json")
    d.set_defaults(func=cmd_discover)

    e = sub.add_parser("emit", help="turn candidates into records")
    e.add_argument("--manifest", default="devboard-cad-candidates.json")
    e.add_argument("--start", type=int, default=0)
    e.add_argument("--count", type=int, default=0, help="0 means all")
    e.add_argument("--overwrite", action="store_true")
    e.add_argument("--verbose", action="store_true")
    e.set_defaults(func=cmd_emit)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
