"""Read each board's hardware licence from the manufacturer's own files (issue #28 s12).

Licensing is the part of this database that does not automate, and ``commercial_use_allowed``
is the field a downstream user actually relies on, so the rule here is narrow: this tool
reads the manufacturer's own licence text and matches it against a table of licences whose
terms are already settled. It never interprets novel prose. A statement it does not
recognise leaves the record at UNVERIFIED, which is the honest outcome and is what the
CI gate requires before any permission may be recorded.

The distinction that matters is between reading and inferring. "SparkFun hardware is
released under Creative Commons Share-alike 4.0 International", quoted from LICENSE.md, is
a reading. Concluding that a board is probably CC-licensed because its vendor usually is
would be an inference, and is not done.

One case recurs and is handled explicitly: Adafruit's READMEs name "Creative Commons
Attribution, Share-Alike" without a version, and the license.txt they point at is often
absent from the repository. Every CC BY-SA version permits commercial use and modification
under attribution and share-alike -- the non-commercial variants are separately named
BY-NC-SA -- so the permissions are determinable while the version is not. Both facts are
recorded.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parents[1]))

from devboard_cad.harvest_github import _gh_api  # noqa: E402
from devboard_cad.verify import derive_status, records_dir  # noqa: E402

# name -> (url, redistribution, modification, commercial, attribution)
KNOWN: Dict[str, Tuple[str, bool, bool, bool, bool]] = {
    "CC BY 4.0":      ("https://creativecommons.org/licenses/by/4.0/", True, True, True, True),
    "CC BY 3.0":      ("https://creativecommons.org/licenses/by/3.0/", True, True, True, True),
    "CC BY-SA 4.0":   ("https://creativecommons.org/licenses/by-sa/4.0/", True, True, True, True),
    "CC BY-SA 3.0":   ("https://creativecommons.org/licenses/by-sa/3.0/", True, True, True, True),
    "CC BY-NC-SA 4.0": ("https://creativecommons.org/licenses/by-nc-sa/4.0/", True, True, False, True),
    "CC BY-NC 4.0":   ("https://creativecommons.org/licenses/by-nc/4.0/", True, True, False, True),
    "CC0 1.0":        ("https://creativecommons.org/publicdomain/zero/1.0/", True, True, True, False),
    "MIT":            ("https://opensource.org/license/mit", True, True, True, True),
    "Apache-2.0":     ("https://www.apache.org/licenses/LICENSE-2.0", True, True, True, True),
    "BSD-3-Clause":   ("https://opensource.org/license/bsd-3-clause", True, True, True, True),
    "BSD-2-Clause":   ("https://opensource.org/license/bsd-2-clause", True, True, True, True),
    "GPL-3.0":        ("https://www.gnu.org/licenses/gpl-3.0.html", True, True, True, True),
    "CERN-OHL-P-2.0": ("https://cern-ohl.web.cern.ch/", True, True, True, True),
    "CERN-OHL-W-2.0": ("https://cern-ohl.web.cern.ch/", True, True, True, True),
    "CERN-OHL-S-2.0": ("https://cern-ohl.web.cern.ch/", True, True, True, True),
    "TAPR-OHL-1.0":   ("https://tapr.org/the-tapr-open-hardware-license/", True, True, True, True),
    "Unlicense":      ("https://unlicense.org/", True, True, True, False),
    # Named but unversioned. Determinable permissions, undeterminable version.
    "CC BY-SA (version not stated by the manufacturer)":
        (None, True, True, True, True),
}

SPDX_ALIASES = {
    "CC-BY-4.0": "CC BY 4.0", "CC-BY-3.0": "CC BY 3.0",
    "CC-BY-SA-4.0": "CC BY-SA 4.0", "CC-BY-SA-3.0": "CC BY-SA 3.0",
    "CC-BY-NC-SA-4.0": "CC BY-NC-SA 4.0", "CC-BY-NC-4.0": "CC BY-NC 4.0",
    "CC0-1.0": "CC0 1.0", "MIT": "MIT", "Apache-2.0": "Apache-2.0",
    "BSD-3-Clause": "BSD-3-Clause", "BSD-2-Clause": "BSD-2-Clause",
    "GPL-3.0": "GPL-3.0", "GPL-3.0-only": "GPL-3.0", "GPL-3.0-or-later": "GPL-3.0",
    "CERN-OHL-P-2.0": "CERN-OHL-P-2.0", "CERN-OHL-W-2.0": "CERN-OHL-W-2.0",
    "CERN-OHL-S-2.0": "CERN-OHL-S-2.0", "Unlicense": "Unlicense",
}

# Ordered: a versioned match must win over the unversioned fallback.
TEXT_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (r"creative commons[^.\n]{0,40}attribution\s*[,/ -]\s*share[- ]?alike[^.\n]{0,20}4\.0", "CC BY-SA 4.0"),
    (r"creative commons[^.\n]{0,40}share[- ]?alike[^.\n]{0,20}4\.0", "CC BY-SA 4.0"),
    (r"licenses/by-sa/4\.0", "CC BY-SA 4.0"),
    (r"licenses/by-sa/3\.0", "CC BY-SA 3.0"),
    (r"licenses/by-nc-sa/4\.0", "CC BY-NC-SA 4.0"),
    (r"licenses/by/4\.0", "CC BY 4.0"),
    (r"\bCC[- ]BY[- ]SA[- ]?4\.0\b", "CC BY-SA 4.0"),
    (r"\bCC[- ]BY[- ]?4\.0\b", "CC BY 4.0"),
    (r"\bCERN[- ]OHL[- ]?P\b", "CERN-OHL-P-2.0"),
    (r"\bCERN[- ]OHL[- ]?W\b", "CERN-OHL-W-2.0"),
    (r"\bCERN[- ]OHL[- ]?S\b", "CERN-OHL-S-2.0"),
    (r"\bTAPR open hardware license\b", "TAPR-OHL-1.0"),
    (r"creative commons attribution\s*[,/]?\s*share[- ]?alike",
     "CC BY-SA (version not stated by the manufacturer)"),
)


def spdx_for(repo: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (licence name, url) from GitHub's own detection, when it is conclusive."""
    try:
        payload = _gh_api(f"repos/{repo}/license")
    except Exception:  # noqa: BLE001 - no LICENSE file is a normal outcome
        return None, None
    spdx = ((payload.get("license") or {}).get("spdx_id") or "").strip()
    name = SPDX_ALIASES.get(spdx)
    return (name, payload.get("html_url")) if name else (None, None)


def _text(repo: str, path: str) -> str:
    try:
        payload = _gh_api(f"repos/{repo}/contents/{path}")
        if isinstance(payload, dict) and payload.get("content"):
            return base64.b64decode(payload["content"]).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        pass
    return ""


LICENCE_FILE = re.compile(r"^(licen[cs]e|copying)(\.(md|markdown|txt))?$", re.I)
LICENCE_FILE_FALLBACK = ("LICENSE.md", "LICENSE", "license.txt", "LICENSE.txt", "COPYING")


def licence_files(repo: str) -> List[str]:
    """The licence files at the repository root, whatever their case.

    GitHub paths are case-sensitive, so asking for a fixed list of spellings misses
    SparkFun's ``license.md`` and ``License.md``: boards whose manufacturer states the
    licence in so many words stayed UNVERIFIED. Listing the root finds every spelling.
    """
    try:
        listing = _gh_api(f"repos/{repo}/contents")
    except Exception:  # noqa: BLE001 - fall back to the known spellings
        return list(LICENCE_FILE_FALLBACK)
    if not isinstance(listing, list):
        return list(LICENCE_FILE_FALLBACK)
    names = [e.get("name", "") for e in listing if isinstance(e, dict) and e.get("type") == "file"]
    return sorted((n for n in names if LICENCE_FILE.match(n)), key=lambda n: (n.lower().startswith("copying"), n))


def readme_text(repo: str) -> str:
    """The repository README through GitHub's readme endpoint, which ignores case."""
    try:
        payload = _gh_api(f"repos/{repo}/readme")
        if isinstance(payload, dict) and payload.get("content"):
            return base64.b64decode(payload["content"]).decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        pass
    return ""


def read_statement(repo: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (licence name, url, quoted sentence) read from the manufacturer's files."""
    for path in licence_files(repo):
        body = _text(repo, path)
        if body:
            for pattern, name in TEXT_PATTERNS:
                if re.search(pattern, body, re.I):
                    return name, f"https://github.com/{repo}/blob/HEAD/{path}", _quote(body, pattern)
    readme = readme_text(repo)
    if readme:
        for pattern, name in TEXT_PATTERNS:
            if re.search(pattern, readme, re.I):
                return name, f"https://github.com/{repo}", _quote(readme, pattern)
    return None, None, None


def _quote(body: str, pattern: str) -> str:
    match = re.search(pattern, body, re.I)
    if not match:
        return ""
    start = max(0, body.rfind("\n", 0, match.start()) + 1)
    end = body.find("\n", match.end())
    line = body[start:end if end != -1 else len(body)].strip(" *#>-\t")
    return re.sub(r"\s+", " ", line)[:200]


def apply_licence(record: Dict[str, Any], name: str, url: Optional[str],
                  quote: Optional[str], source: str) -> bool:
    fallback_url, redist, modify, commercial, attribution = KNOWN[name]
    licenses = record["licenses"]
    before = json.dumps(licenses, sort_keys=True)
    licenses["hardware_license"] = name
    licenses["license_url"] = url or fallback_url or source
    for field in ("cad_license", "schematic_license", "pcb_license",
                  "mechanical_cad_license"):
        licenses[field] = name
    licenses["redistribution_allowed"] = redist
    licenses["modification_allowed"] = modify
    licenses["commercial_use_allowed"] = commercial
    licenses["attribution_required"] = attribution
    note = f" Hardware licence read from {source}"
    if quote:
        note += f': "{quote}"'
    note += "."
    if name.startswith("CC BY-SA (version"):
        note += (" No version is given and the license file the README points at is not "
                 "present, so the version is unverified; every CC BY-SA version permits "
                 "commercial use and modification under attribution and share-alike, so "
                 "the permissions are recorded and the version is not.")
    if note not in (record.get("notes") or ""):
        record["notes"] = (record.get("notes") or "") + note
    return json.dumps(licenses, sort_keys=True) != before


def repo_slug(record: Dict[str, Any]) -> str:
    repo = record["sources"].get("official_github_repository") or ""
    return repo.split("github.com/", 1)[1].strip("/") if "github.com/" in repo else "its repository"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(REPO_ROOT))
    parser.add_argument("--overwrite", action="store_true",
                        help="re-read even when a licence is already recorded")
    args = parser.parse_args(argv)

    read = unknown = 0
    for path in sorted(records_dir(Path(args.root).resolve()).glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        licenses = record["licenses"]
        current = str(licenses.get("hardware_license", "")).strip()
        undecided = all(licenses.get(f) is None for f in
                        ("redistribution_allowed", "modification_allowed",
                         "commercial_use_allowed"))
        # A licence name with no permissions behind it is invisible to the commercial-reuse
        # queries. harvest_github records GitHub's SPDX tag as the name, so those records
        # arrive named but undecided and must still be resolved.
        if current and current.upper() != "UNVERIFIED" and not undecided and not args.overwrite:
            continue
        if current and current.upper() != "UNVERIFIED" and undecided:
            name = SPDX_ALIASES.get(current, current if current in KNOWN else None)
            if name:
                apply_licence(record, name, None, None,
                              f"the SPDX licence GitHub detects for {repo_slug(record)}")
                record["record_status"] = derive_status(record)
                with path.open("w", encoding="utf-8", newline="\n") as handle:
                    json.dump(record, handle, indent=2)
                    handle.write("\n")
                read += 1
                print(f"  {record['board_id']:44} {name} (permissions filled)", flush=True)
                continue
        repo = record["sources"].get("official_github_repository")
        if not repo or "github.com/" not in repo:
            unknown += 1
            continue
        slug = repo.split("github.com/", 1)[1].strip("/")
        name, url = spdx_for(slug)
        quote = None
        source = f"the SPDX licence GitHub detects for {slug}"
        if not name:
            name, url, quote = read_statement(slug)
            source = f"{slug}"
        if not name or name not in KNOWN:
            unknown += 1
            continue
        if apply_licence(record, name, url, quote, source):
            record["record_status"] = derive_status(record)
            with path.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(record, handle, indent=2)
                handle.write("\n")
            read += 1
            print(f"  {record['board_id']:44} {name}", flush=True)
    print(f"\nlicences read={read}  left unverified={unknown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
