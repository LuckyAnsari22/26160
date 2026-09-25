# PS 26160 — AI-Powered IPsec VPN Protocol Analyzer
## Project Status: What's Implemented, What's Verified, What's Still Broken

> Last updated: 2026-09-25 (revision 7 — `frontend/index.html`'s six schema mismatches fixed and re-verified live against the running backend, zero blank pages/console errors across every real status combination)
> This file supersedes the honesty-tag checklist in `build_log.md` for anything it contradicts — everything below reflects what was actually run and observed in this session, not what earlier docs claimed.

---

## 1. How to read this document

Every claim below is tagged:
- **✅ VERIFIED** — actually run, actual output observed and checked (not just "should work")
- **🟡 IMPLEMENTED, PARTIALLY VERIFIED** — code is real and correct for the cases tested, but not every path has been exercised
- **🔴 BROKEN / NOT DONE** — known issue, not yet fixed
- **⚫ BLOCKED** — cannot proceed until an external condition (usually: Docker) is resolved

---

## 2. Environment

| Item | Status | Detail |
|---|---|---|
| Docker Desktop | ✅ VERIFIED installed and healthy | v4.91.0 / Docker Engine 29.8.0, WSL2 backend, Ubuntu is the default WSL distro |
| Docker daemon health | ✅ **FIXED** | Had crashed (`unexpected EOF`) writing a 184MB pcap because its data disk lived on a nearly-full C:. **Data disk relocated to `D:\DockerDesktopWSL`** (confirmed: old `%LOCALAPPDATA%\Docker\wsl\disk` is now empty, new location exists, C: free space jumped from ~57MB to 3.35GB). `docker ps`/`docker info` now respond instantly. |
| C: drive free space | 🟡 IMPROVED, still worth watching | Went from ~57MB to 3.35GB free after the Docker relocation. Still tight for a 274GB drive — general cleanup is still worth doing independent of this project. |
| Python packages | ✅ VERIFIED | `scapy==2.5.0` installed (was missing entirely — required for `IKEParser` and `SPLTFeatureExtractor` to function at all). Installed to `D:\tmp_pip\scapy_install` via `--target` (not default site-packages, since default site-packages is also on the full C: drive) — **anyone running this code needs `PYTHONPATH=D:\tmp_pip\scapy_install`** until scapy is reinstalled normally once C: has room, or a venv is created on D:. |
| `requirements.txt` | ✅ FIXED | Removed `pyshark` (dead dependency, never imported anywhere). Added `matplotlib`, `shap`, `joblib`, `fpdf2`, `requests` — all actually imported by existing code but previously missing, so `pip install -r requirements.txt` was insufficient to run half the repo. |

---

## 3. Testbed (`testbed/`)

### 3.1 Fixed this session

| Bug | File | Fix |
|---|---|---|
| `moon`/`sun` containers failed to start at all (`Address already in use`) | `docker-compose.yml` | Docker auto-assigns a bridge network's `.1` address as its own gateway, but `moon`/`sun` were also statically assigned to `.1` on `net-alice`/`net-bob`. Added explicit `gateway:` overrides (`.254`) on all three networks (v4 + v6). |
| charon (the IKE daemon) never started — `swanctl` couldn't reach its VICI socket, guaranteeing every SA attempt failed | `entrypoint-gateway.sh` | Hardcoded `/usr/lib/ipsec/charon` (Debian/Ubuntu path). Alpine's strongswan package installs it at `/usr/lib/strongswan/charon`. **This is almost certainly the real root cause of every "FAIL (SA: DOWN)" in the original `build_log.md`/`test_results.log`**, independent of the earlier Docker-not-installed issue. |
| `generate_traffic.sh` captured on the wrong interface | `scripts/generate_traffic.sh` | Hardcoded `-i eth1` as "the WAN link." Verified empirically that interface naming is **not consistent** across containers: on `moon`, `eth0` is WAN; on `sun`, `eth1` is WAN. Now detects the WAN interface dynamically by IP match (`ip -o -4 addr show \| grep '10\.0\.0\.'`) instead of a hardcoded name. |
| Video/VoIP traffic generation could leak into the next capture window | `scripts/generate_traffic.sh` | Was backgrounding `docker compose exec ... iperf3 &` then `kill $!` — that only kills the local `docker compose exec` client process, not the remote `iperf3` inside the container. Replaced with iperf3's own `-t` duration flag (matching how "bulk" already worked), removing the race entirely. |
| **No IKE handshake in any capture** | `switch_config.sh`, `scripts/generate_traffic.sh` | `switch_config.sh` always called `swanctl --initiate` before `generate_traffic.sh` could start `tcpdump`, so every capture had 0 IKE packets. Added a `--no-initiate` flag to `switch_config.sh`; `generate_traffic.sh` now brings the gateways up without initiating, starts a dedicated `tcpdump` first, *then* initiates, capturing the real handshake into its own `${variant}_ike_handshake.pcap` before proceeding to the normal traffic-type captures. **Verified working**: manually smoke-tested end-to-end, produced a real 4-packet capture with a genuine IKE_SA_INIT exchange (see §5 for what this unlocked). |
| Uncapped "bulk" traffic crashed Docker | `scripts/generate_traffic.sh` | Uncapped TCP `iperf3` saturated the Docker bridge, producing 184MB in 15s, which crashed the daemon by filling its (then C:-based) VM disk mid-write. Capped at `-b 10M` (~18MB per capture instead) — still a genuine sustained bulk-transfer shape for feature-extraction purposes, since the ML features are per-flow aggregate stats, not raw byte counts. |

### 3.2 The single biggest finding this session: Scapy cannot dissect IKEv2 SA/Proposal/Transform payloads into text at all

Capturing a real IKE handshake for the first time (see above) let `ike_parser.py` be tested against genuine traffic for the first time in this project's history. Result: **every single crypto field came back empty** despite the handshake genuinely negotiating `AES_GCM_16-256/PRF_HMAC_SHA2_256/ECP_256` (confirmed independently via the live `swanctl --list-sas` log at capture time).

Root cause, confirmed by dumping Scapy's actual dissection output: Scapy's ISAKMP layer only parses the outer payload header (`next_payload`, `length`) — it does **not** decode the SA payload's nested Proposal/Transform sub-structure into readable field names at all. `pkt.show(dump=True)` never contains strings like `"AES_GCM_16_256"` or `"Group 19"` for a real packet; the parser's entire string-matching design only ever worked against a hand-written mock string in the test suite that happened to contain exactly those substrings, and never once against real traffic.

**Fixed properly, not patched around**: `ike_parser.py` now does real binary parsing of the IKEv2 SA payload per RFC 7296 Section 3.3 (Proposal Substructure → Transform Substructure → Transform Attributes for key length), walking Scapy's actual payload chain via real bytes (`.load`), not text. Hand-decoded and verified byte-for-byte against the real capture before writing the implementation: Transform ID 20 (`ENCR_AES_GCM_16`) + Key Length attribute 256 → `"AES-GCM-256"`; PRF ID 5 → `"SHA256"`; DH Transform ID 19 → `"ECP_256"` — **exactly matching what strongSwan itself logged as negotiated.**

**Also discovered and correctly left unfixed** (because it's a protocol constraint, not a code bug): `mode` (Tunnel/Transport) and `pfs` are negotiated inside the IKE_AUTH / CREATE_CHILD_SA exchange, which is **encrypted** (wrapped in an SK payload) as soon as the IKE_SA exists. A passive observer without the derived keys structurally cannot see either field — no parser, however well-written, can extract them from ciphertext. The old code's attempt to detect these via text substrings (`"Tunnel"`, `"CREATE_CHILD_SA"`) never worked for the same reason the crypto fields didn't — it's now removed and replaced with an honest, documented "always UNKNOWN/False, and here's exactly why" rather than dead code pretending to try.

**Downstream consequence this also surfaced and fixed**: because PFS can never be confirmed from a short capture, `rule_engine.py`'s default-to-disabled assumption was producing a **HIGH-severity "PFS disabled" finding** (capping the score at 59) on a capture from the variant literally named `tunnel-aes256gcm-ecp256-pfs`. Fixed in `main.py` (not in the trusted `rule_engine.py`): when no `CREATE_CHILD_SA` exchange was observed in the capture, that specific finding is stripped and the score recomputed, with an explicit `"caveats"` field explaining this is a capture-visibility limit, not a confirmed misconfiguration. Verified: the same real capture now correctly scores 100/100 with an honest caveat, instead of a false 59/100.

### 3.3 Verified end-to-end (one variant, real traffic, real capture)

`tunnel-aes256gcm-ecp256-pfs` (Tunnel mode, AES-256-GCM, ECP256/DH-19, PFS) was brought up and checked at every layer, not assumed:
- IKE SA: **ESTABLISHED** (matching SPIs on both `moon` and `sun`, negotiated `AES_GCM_16-256/PRF_HMAC_SHA2_256/ECP_256` — exactly the requested variant)
- CHILD SA: **INSTALLED**, `TUNNEL` mode, `ESP:AES_GCM_16-256`, correct traffic selectors `192.168.1.0/24 === 192.168.2.0/24`
- Real traffic crossed the tunnel: ping 0% loss, ESP SA byte/packet counters incremented exactly matching the ping count
- Real PCAP captured and independently parsed byte-by-byte (not trusted blindly): valid pcap magic header, packets confirmed as genuine ESP (protocol 50)
- **New this revision**: a real IKE_SA_INIT handshake was also captured and correctly parsed end-to-end through the live API (see §3.2 and §5)

### 3.4 Transport mode was completely non-functional — found via verification, now fixed

A dedicated verification pass (not this fix pass) caught this: variant 5 (`transport-aes256gcm-ecp256-pfs`) produced an IKE handshake fine, but **every traffic-type capture was empty (0 packets)**, and the run stalled badly (136s instead of ~15s) partway through. Root-caused with direct kernel evidence, not guessed:

1. `swanctl --list-sas` showed the transport SA genuinely `ESTABLISHED`/`INSTALLED` with correct selectors (`local 10.0.0.1/32, remote 10.0.0.2/32`) but **0 bytes/0 packets** transferred even after 200+ seconds of alice pinging bob through the gateways. Transport mode only ever protects traffic between the two IPsec endpoints themselves (moon↔sun) — it structurally cannot protect alice→bob traffic transiting through them. **Fix**: `generate_traffic.sh` now detects `transport-*` variants and generates traffic directly moon→sun (with `iperf3`/`curl`/`python3` added to their image, and matching servers set up on `sun`) instead of alice→bob.
2. Even after fixing that, a manual moon→sun ping *still* produced 0 bytes across the SA. Checked the actual kernel state directly (`ip xfrm policy`/`ip xfrm state`) rather than trusting `swanctl`: found strongSwan's **`bypass-lan` plugin** had installed a broad `10.0.0.0/24 ↔ 10.0.0.0/24` bypass (cleartext passthrough) policy, because moon and sun sit on the *same* Docker subnet as each other — a lab-topology artifact that essentially never happens in real deployments (peers are basically never on the same L2 segment as each other). This bypass policy shadowed the SA's own narrow policy entirely. **Fix**: disabled `bypass-lan` for moon/sun via a `strongswan.d/charon/bypass-lan.conf` override baked into the image (`testbed/bypass-lan.conf`).
3. **Verified after both fixes**: `ip xfrm policy` now shows the correct narrow `10.0.0.1/32 → 10.0.0.2/32` IPsec policy (no bypass), and a manual ping incremented the SA counters from `0/0` to exactly `3 packets, 192 bytes` matching the ping — the first time in this project's history that Transport mode has actually protected any traffic.
4. **A third bug, found only by checking actual packet counts instead of trusting "file exists and is >100 bytes"**: after fixes 1+2, the automated run's `icmp` capture for variant 5 was genuinely real (9024 bytes), but `bulk`/`video`/`voip` were each only 2 packets (110+90 bytes - a single failed connection attempt) and `web`/`email` were 10 packets (5× the same failed 2-packet pattern). Root cause: `sun`'s iperf3/http.server/nc servers were started **once, before the variant loop began** - but `switch_config.sh --force-recreate`s `sun` fresh for every variant to load its new swanctl config, which kills any background processes from before that recreate. `icmp` worked because it doesn't need a server (ICMP echo is handled by the kernel); everything else silently failed to connect. **Fix**: moved the `sun` server setup into a function, called *after* `switch_config.sh` for each transport variant, not once up front.
5. **A fourth, unrelated bug found the same way (checking packet counts, not just file existence), this time on the IPv6 variant**: `web.pcap` for `tunnel-aes256gcm-ecp256-pfs-ipv6` was 24 bytes (empty). Verified directly: `curl http://fd02::10/...` was rejected outright (`URL rejected: Port number was not a decimal number`) - an IPv6 literal in a URL needs brackets (`http://[fd02::10]/...`). **Fixed** the URL construction, which then revealed a *fifth* bug: with a valid bracketed URL, the request still failed, because on this Alpine/musl environment binding `python3 -m http.server` to `::` is **IPv6-only**, not dual-stack (unlike the glibc default most people assume) - it silently stopped accepting the IPv4 connections 7 of the 8 variants depend on. **Fixed** by running two separate `http.server` instances on different ports (80 for IPv4, 8080 for IPv6) rather than trying to share one dual-stack socket.

### 3.5 Full 8-variant dataset generation — ✅ COMPLETE AND VERIFIED

All 8 variants × 7 captures each (1 IKE handshake + 6 traffic types) = **56/56 real, correctly-sized captures**, independently verified via `scapy.rdpcap` packet counts (not just file size) for every single file - zero empty, zero truncated, zero missing, zero orphaned manifest rows. `data/raw/dataset_manifest.csv` was also deduplicated (11 stale duplicate rows from mid-run redo cycles removed, keeping the final correct capture of each file).

Also closes an item flagged earlier as unverified: the real 3DES/SHA1/MODP1024 handshake (`tunnel-weak-3des-sha1-modp1024`) run through the live API correctly populated `integrity_algorithm: ["SHA1"]` - confirming the binary SA-payload parser (§3.2) works correctly for a CBC+HMAC-style proposal (separate integrity transform), not just the AEAD/no-integrity-transform case it was first verified against. Compliance output was fully correct: 3DES→SWEET32 (HIGH), SHA1→deprecated (MEDIUM), MODP_1024/Group 2→Logjam (HIGH), score capped at 59, with the honest PFS caveat rather than a false "disabled" finding.

**Process note for next time**: editing `generate_traffic.sh` while a background invocation of it was still running corrupted the running interpreter's control flow once (`continue: only meaningful in a for loop`, then a syntax error) - bash does not isolate a running script from concurrent edits to its own source file. Don't edit a script's file while a background job is still executing it, even if the edit targets a part of the file "already past" - if that part is inside a function invoked again later in a loop, the running instance can still be affected.

### 3.6 Still broken / not done

| Issue | Status | Detail |
|---|---|---|
| `setup_strongswan.sh` | 🔴 DEAD / CONTRADICTS DOCS | Uses the deprecated `ipsec.conf`/`ipsec.secrets` format that `research_dossier.md` explicitly says not to use. Not called by anything. Not fixed (out of scope so far — flagging for cleanup). |
| `docker-compose.yml` `version:` key | 🟡 COSMETIC | Obsolete, generates a warning on every command. Harmless but not cleaned up. |

---

## 4. Backend (`backend/`)

### 4.1 `main.py` — fully rewritten, verified via real HTTP requests

The single most serious issue in the original audit was that `POST /api/v1/analyze` ignored the uploaded file entirely and returned a hardcoded dict. **This is fixed and verified, not just rewritten:**

| Test | Input | Result | Status |
|---|---|---|---|
| Garbage input rejection | `dummy.pcap` (5 literal bytes) | `{"status": "error", "error": "Not a valid pcap file: Not a supported capture file"}` | ✅ VERIFIED |
| Real pcap, full pipeline | Real testbed capture (60 pkts) | Real compliance (`indeterminate` — correctly reasoned, no IKE observed), real classification (see §5.2 for the honest result) | ✅ VERIFIED |
| No ESP, no IKE at all | Constructed test fixture | Both compliance and classification correctly `indeterminate`, distinct reasons | ✅ VERIFIED |
| ESP present, below 20-packet floor | Constructed test fixture (10 pkts) | Classification correctly `indeterminate`: *"10 ESP packets observed, but no flow met the 20-packet minimum"* | ✅ VERIFIED |
| `/api/v1/export/{id}` | Real analysis ID | Returns an actual `application/pdf` file (`%PDF-1.3` magic bytes, 2550 bytes) instead of the old `{"download_url": "stubbed_for_demo"}` | ✅ VERIFIED |
| `/api/v1/export/{id}` | Unknown ID | Still correctly 404s | ✅ VERIFIED |

What `process_pcap()` now actually does: validates the pcap once (real IKE/ESP packet counts), runs `IKEParser` → `SecurityRuleEngine`, runs `SPLTFeatureExtractor` → the loaded `calibrated_rf_model.pkl` → `adversarial_padding.py`'s real `apply_mtu_padding`/`apply_adaptive_padding`. **No hardcoded fallback values remain anywhere in the file.** `scapy` is imported at module level (not swallowed in try/except) so a missing dependency fails the server loudly at startup instead of silently degrading every request to fake-looking "indeterminate."

### 4.2 Known limitations of the current wiring

- SHAP explanation is **not** wired into live requests (the old hardcoded `shap_explanation` block was removed, not replaced with a live equivalent — computing live TreeSHAP against a `CalibratedClassifierCV`-wrapped model is nontrivial and was out of scope for this pass).
- `report_generator.py` itself is still hardcoded (see §6) — `/export` now genuinely calls it and returns a real file, but that file's *content* is still static text, not derived from the specific analysis ID requested.
- Redundant pcap reads: `main.py`'s validation pass, `IKEParser`, and `SPLTFeatureExtractor` each independently call `rdpcap()` on the same file (3 reads total). Not fixed — correctness was prioritized over this performance nitpick in this pass.

---

## 5. ML Pipeline (`ml_pipeline/`)

### 5.1 Real bugs found and fixed this session

| Bug | File | Detail |
|---|---|---|
| Bidirectional ESP flows silently split in two | `feature_extractor.py` | `_get_flow_key()` included the packet's ESP SPI, but inbound/outbound ESP traffic uses **different** SPIs per RFC 4303. This split one genuine tunnel conversation into two fake unidirectional "flows" (both `direction_ratio=1.0`). **Verified fix**: re-ran against the real capture — went from 2 flows to the correct 1 flow (`direction_ratio=0.5`, properly balanced). |
| **Entire crypto-field extraction non-functional against real traffic** | `parser/ike_parser.py` | Full rewrite — see §3.2 for the complete story. Scapy never renders IKEv2 SA/Proposal/Transform payloads as readable text; the old string-matching approach could not work against any real packet, only a hand-written mock. Replaced with real RFC 7296 binary parsing, verified byte-for-byte against a genuine captured handshake and cross-checked against strongSwan's own `swanctl --list-sas` output for that same handshake. `mode`/`pfs` detection (also broken the same way) was removed rather than re-broken differently — both are provably unobservable from a passive capture, documented as such. |
| DH group detection silently failing on valid input | `parser/ike_parser.py` | Found via a newly-fixed test, before the full rewrite above superseded it. Original bug: DH-group detection was gated behind `"DH" in pkt_repr or "Diffie-Hellman" in pkt_repr`, but the markers it searched for (`"Group 19"` etc.) don't co-occur with "DH" in real dissection output. Moot now that the string-matching approach is gone entirely, but the fix history is preserved here since it's what led to discovering the bigger issue. |

### 5.2 Honest result: the trained model is currently wrong on real traffic

After the flow-key fix above, the real ICMP capture (genuinely ICMP traffic) is classified by `calibrated_rf_model.pkl` as **"email" at 80% confidence** — a real, verified misclassification, not a bug in the wiring. Before the fix it said "icmp" at 41% confidence (also arguably "right for the wrong reason," since the pre-fix feature vector was itself wrong).

**Root cause:** the model is trained entirely on `generate_synthetic_features.py`'s hand-fabricated data (see the earlier `code_audit_report.md` for the full finding), where the "icmp" class was hand-built with a specific narrow statistical shape that doesn't match how real, correctly-extracted bidirectional ICMP traffic actually looks (`mean_iat` and `direction_ratio` differ substantially). This is not a wiring bug — the pipeline is doing exactly what it should; the *model* needs retraining on real data. Flagged for you separately: **the "ISCXVPN2016 Generalization Validation: 99.44%" claim in `build_log.md` is still unaddressed** — it was never real (see `code_audit_report.md` §"Classifier + calibration + SHAP" for the full finding) and this session's real-world test is independent, additional evidence that synthetic training data does not reflect real captured traffic.

### 5.3 Tests fixed

| Fix | File |
|---|---|
| `test_parser_extraction_mocked` was previously **SKIPPED** (scapy wasn't installed, so it never actually ran). Its `MockPacket` was missing `__getitem__`, so `pkt[ISAKMP].version` threw `TypeError`, silently caught by the parser's broad `except`, making every assertion fail once the test could actually execute. First fix: patched the mock. | `tests/test_rule_engine.py` |
| **Replaced entirely**, not just patched, once the parser rewrite (§3.2) made the mock obsolete: the mock modeled the OLD (broken) text-scraping mechanism, which no longer exists. `test_parser_extraction_mocked` → `test_parser_extraction_real_pcap`, now runs `IKEParser` against a genuine captured IKE_SA_INIT handshake saved as a permanent fixture, asserting the real extracted values (`AES-GCM-256`, `SHA256`, `ECP_256`) plus the honest `mode="UNKNOWN"`/`pfs=False` defaults. | `tests/test_rule_engine.py`, `tests/fixtures/real_ike_sa_init_aes256gcm_ecp256.pcap` (new) |

**Current test status: 13/13 passing**, three of which exercise real captured protocol data instead of a hand-written mock (see §5.3.1 for the two added after this revision).

### 5.3.1 `ike_parser.py` verified against two more real proposal shapes — both correct on the first try, no fixes needed

The AES-GCM fixture (§5.3) only ever exercised an AEAD proposal, which has no separate integrity transform - it couldn't verify `integrity_algorithm` extraction at all. Two more real captures from the completed 8-variant dataset (§3.5) were added as permanent fixtures specifically to close that gap and exercise different Transform ID values entirely:

| Fixture | Variant | strongSwan's own log (ground truth) | `IKEParser` output | Match |
|---|---|---|---|---|
| `real_ike_sa_init_aes256cbc_sha1_modp2048.pcap` | `tunnel-aes256cbc-sha1-modp2048-nopfs` | `AES_CBC-256/HMAC_SHA1_96/PRF_HMAC_SHA1/MODP_2048` | `AES-CBC-256` / `SHA1` (integ) / `SHA1` (prf) / `MODP_2048` | ✅ exact |
| `real_ike_sa_init_3des_sha1_modp1024.pcap` | `tunnel-weak-3des-sha1-modp1024` | `3DES_CBC/HMAC_SHA1_96/PRF_HMAC_SHA1/MODP_1024` | `3DES` / `SHA1` (integ) / `SHA1` (prf) / `MODP_1024` | ✅ exact |

Also hand-decoded the raw SA payload bytes for both (not just trusted the parser's own output) to confirm the actual Transform ID values on the wire:
- **CBC+HMAC**: 4 transforms present in the proposal (vs GCM's 3) - Encryption Transform ID **12** (`ENCR_AES_CBC`) + a Key Length attribute of 256, Integrity Transform ID **2** (`AUTH_HMAC_SHA1_96`), PRF Transform ID **2** (`PRF_HMAC_SHA1`), DH Transform ID **14** (`MODP_2048`/Group 14).
- **Weak/legacy**: Encryption Transform ID **3** (`ENCR_3DES`, no Key Length attribute - 3DES has a fixed key size, unlike AES), Integrity Transform ID **2**, PRF Transform ID **2**, DH Transform ID **2** (`MODP_1024`/Group 2).

Both matched the parser's output and strongSwan's log exactly. **No parser changes were needed** - unlike the original AES-GCM finding, this was a clean verification pass, not a bug hunt. Added as `test_parser_extraction_real_pcap_cbc_hmac` and `test_parser_extraction_real_pcap_weak_legacy` in `tests/test_rule_engine.py`; also tightened the original AES-GCM test to explicitly assert `integrity_algorithm == []`, making the AEAD-vs-CBC contrast a first-class assertion instead of an implicit gap.

### 5.4 Tunnel-vs-Transport mode inference — built, honestly evaluated, and it's genuinely unreliable at this sample size

The PS requires AI-based identification of Tunnel vs Transport mode. `ike_parser.py` correctly reports this as `"UNKNOWN"` from cleartext (mode is negotiated inside the encrypted IKE_AUTH/CREATE_CHILD_SA exchange - that finding is correct and untouched). The task here was a **separate, defensible statistical signal**: Tunnel mode ESP-encrypts the entire original IP packet (own IP header included); Transport mode does not. So the ESP ciphertext itself should be structurally larger in Tunnel mode by roughly the inner IP header size (20B IPv4 / 40B IPv6), modulo cipher padding and MTU effects.

**Added `esp_mean_len`/`esp_std_len`/`esp_min_len`/`esp_max_len`** to `feature_extractor.py`, computed from `pkt[ESP].data`'s length (scapy's own dissection of the ESP ciphertext, excluding SPI/seq and *all* outer-header bytes - verified to be outer-IP-version-agnostic, which matters: one variant in this dataset has an IPv6 *outer* WAN, which would otherwise confound a naive "total packet length" measurement with an unrelated 20-byte outer-header difference).

**Checked empirically against real captures before building anything on top of it** (theory NOT assumed to hold):
- For matched ciphers, at the individual-packet level, the signal is exact: AES-256-GCM ICMP, Tunnel ESP-payload = 112 bytes, Transport = 92 bytes - a difference of **exactly 20 bytes**, precisely matching the IPv4 inner-header prediction.
- But pooled across the 8 real variants (which mix ciphers), the picture is genuinely mixed: VoIP and Web separate cleanly (Tunnel consistently larger); ICMP does not (cipher-driven overhead differences, themselves ~16-20 bytes, tie or exceed the tunnel/transport signal); **Bulk transfer actually inverts the direction** (Tunnel < Transport) due to MTU/MSS segmentation effects on TCP's effective payload size. A single fixed-direction threshold does not generalize across traffic types.

**Trained and evaluated honestly**: `ml_pipeline/train_mode_classifier.py` fits a simple logistic regression (`esp_mean_len` + `esp_min_len`, selected empirically over 2 other candidates, not assumed) and evaluates it via **leave-one-variant-out cross-validation** (grouped by config variant, not a random split - flows from the same variant aren't independent samples, and a random split would leak the cipher's identity). Result:

> **Balanced accuracy: 0.55** (chance = 0.50) across 8 real testbed variants (6 tunnel, 2 transport). Confusion matrix: 27/30 tunnel flows correctly predicted, but only 2/10 transport flows correctly predicted - the model is close to just predicting the majority class.

**This is reported as unreliable, not dressed up.** Wired into `main.py` as a new `mode_inference` section on every response, but deliberately structured so `predicted_mode` never appears without `reliability: "LOW"` and the actual validated balanced-accuracy number alongside it - the same distinction the PS itself cares about (a judge asking "how did you get this" gets an honest, different answer than for encryption/PRF/DH group, which come from cleartext IKE fields and are reliable by construction). Live-tested against real captures the model hadn't been evaluated on in the LOGO run: correctly predicts a real tunnel/transport VoIP pair; incorrectly predicts transport-mode bulk and ICMP captures as tunnel - consistent with, not contradicting, the honestly-reported 0.55 figure.

Added as permanent test fixtures (`tests/fixtures/real_esp_{tunnel,transport}_{icmp,voip}.pcap`): exact-value assertions on the deterministic feature extraction (ICMP, zero variance, confirms the 20-byte AES-GCM delta precisely), plus one genuinely-correct classifier prediction pair (VoIP) - explicitly documented in the test as one confirmed success case, not a general reliability claim.

**What would actually fix this**: more real captures across more variants, especially more Transport-mode ones (only 2 exist in this dataset vs 6 Tunnel - the class imbalance itself limits what LOGO CV can even measure). This is a data-volume problem, not a modeling problem - a fancier classifier on the same 8 variants would not meaningfully improve on 0.55.

### 5.5 Still not fixed / not done

- ~~`ml_pipeline/adversarial.py`~~ deleted (§6.1).
- Live SHAP explanations are not wired into the API for the traffic-type classifier (see §4.2).
- ~~The model itself has not been retrained on real data~~ done - `models/calibrated_rf_model_real.pkl`, see §5.2 for the honest comparison against the synthetic model.

---

## 6. Dashboard & Reports

### 6.1 Dead code deleted, confirmed dead first

Both grepped for actual imports across the whole repo (including `tests/`) before deleting - only prose mentions in docs, zero code references to either:

- **`ml_pipeline/adversarial.py`** — deleted. Confirmed dead: uses a completely different, incompatible column schema (`min_packet_size`, `total_bytes`, etc.) from every other module's real schema (`min_len`, `pkt_count`, etc.), never imported anywhere. Superseded by `adversarial_padding.py`, which is the one `main.py` actually imports and uses.
- **`frontend/Dashboard.jsx`** — deleted. Confirmed dead: posts to `http://localhost:8000/api/analyze` (missing `/v1/`), expects `report.security_assessment.risk_score` / `report.ai_analysis.*` / `report.protocol_parameters` - none of which exist in `main.py`'s actual response shape. Not referenced by `index.html` (which has its own self-contained inline React, no external `.jsx` import) or anywhere else.

### 6.2 `frontend/index.html` actually tested live in a browser against the running backend — genuinely broken, not just untested

Previously flagged as "not tested in a browser this session." Tested now: opened in the built-in browser against the live `POST /api/v1/analyze` → `GET /api/v1/results/{id}` flow (using a real captured pcap, verified byte-for-byte transferred - 10224 bytes in, 10224 bytes received by the backend), then isolated each further code path with a mocked `fetch` returning main.py's exact real response shapes (verified against actual live API output first, not guessed) to reach every tab/status combination safely. **Every one of these is a live, console-confirmed finding, not a code-reading guess:**

| # | Trigger | What happens | Live-confirmed error |
|---|---|---|---|
| 1 | Any successful analysis with real classification data (the common case) | **Whole page goes blank white**, zero visible indication anything went wrong | `TypeError: Cannot read properties of undefined (reading 'adaptive_confidence')` - dashboard reads `results.countermeasures.adaptive_confidence` (top-level), but main.py actually nests it at `results.classification.countermeasures.adaptive_confidence`. This fires on the CISO tab, which is the default tab shown immediately after any upload - **this crash is not an edge case, it's the normal path.** |
| 2 | SOC Analyst tab, on any capture (after working around #1) | Blank page again | `TypeError: Cannot read properties of undefined (reading 'top_features')` - reads `results.classification.shap_explanation.top_features`. `shap_explanation` was deliberately removed from `main.py` and never wired to a live equivalent (§4.2) - it does not exist in any real response, ever. This is exactly the silent failure asked to be checked for. |
| 3 | Compliance Auditor tab, indeterminate compliance (any capture with no IKE handshake - 8 of this session's own real captures are exactly this) | Blank page | `TypeError: Cannot read properties of undefined (reading 'map')` - reads `results.compliance.findings.map(...)`, but `findings` only exists when `compliance.status === "assessed"`; indeterminate compliance has no `findings` key at all. |
| 4 | SOC Analyst tab, indeterminate classification (any capture with ESP but no matching flow, or no ESP at all) | Blank page | `TypeError: Cannot read properties of undefined (reading 'toUpperCase')` - reads `results.classification.predicted_class.toUpperCase()`; indeterminate classification has no `predicted_class` at all. |
| 5 | CISO tab, indeterminate compliance | **No crash, but displays `NaN/100`** as the Overall Risk Score - `100 - results.compliance.score` where `score` doesn't exist for indeterminate compliance. Worse than a crash in one sense: it looks like real output. |
| 6 | Compliance Auditor tab, any assessed finding | **No crash, silently blank** - every finding's "Severity Cap:" shows nothing. `main.py` names this field `cap_applied`; the dashboard reads `f.cap`. |

**What does work**: the upload form itself, the endpoint URL (`/api/v1/analyze`, correctly includes `/v1/` unlike the deleted Dashboard.jsx), the two `/api/v1/assets/*.png` images (both files genuinely exist on disk), and the CISO tab's Traffic Leakage card (`classification.confidence`/`predicted_class` render correctly when classification succeeds).

**Net assessment at the time**: `index.html` was not a working dashboard - it rendered a blank white page for the majority of real result shapes `main.py` actually produces, and the two cases that didn't hard-crash silently showed wrong data (`NaN/100`, a blank severity cap).

### 6.2.1 Fixed, and re-verified live against the same six failure modes - all six confirmed gone

Each of the 6 rows above traced back to the same root cause: the dashboard read fields assuming every response was a fully "assessed"/"classified" success, when `compliance.status` and `classification.status` can each independently be `assessed`/`indeterminate`/`unavailable`/`classified`/`error`, with a different set of fields present for each. Fixed by branching on `status` before rendering, everywhere a field was read unconditionally before:

| # | Fix |
|---|---|
| 1 | `countermeasures` now read from `classification.countermeasures` (where `main.py` actually puts it), gated on `classification.status === 'classified'`. |
| 2 | The nonexistent `shap_explanation.top_features` panel replaced with `classification.flow_stats` (pkt_count/mean_len/mean_iat/direction_ratio) - real data `main.py` actually sends, labeled honestly ("Live per-request SHAP explanations aren't wired into the API yet"). The static SHAP image is kept but relabeled as a training-time reference, not implied to be per-request. |
| 3 | `compliance.findings.map(...)` now gated on `compliance.status === 'assessed'`; indeterminate/unavailable compliance renders its real `reason` text instead. |
| 4 | `classification.predicted_class.toUpperCase()` now gated on `classification.status === 'classified'`; other statuses render their real `reason` text instead. |
| 5 | The risk-score card now checks `compliance.status === 'assessed'` before computing `100 - score`; otherwise shows a "Not available" card with the real reason, never `NaN`. |
| 6 | `f.cap` → `f.cap_applied` (the field's real name). |
| bonus | `results.status === 'error'` (invalid/empty pcap - `main.py` returns no `compliance`/`classification` keys at all in this case) is now handled before the tabs render at all, instead of falling through into code that assumed those keys exist. |
| bonus | `compliance.caveats` (e.g. the honest PFS-visibility-limit caveat, §3.4) is now surfaced in both the CISO and Auditor views - it existed in the API response all along but was never displayed. |

**Re-verified live, same standard as the original finding** (real uploads through the actual form to the running backend, not just code reading): tested the default classified+indeterminate-compliance case (previously *always* crashed - now renders correctly, including the real "email"-misclassification confidence number from the still-loaded synthetic model), the SOC tab for both classified and indeterminate classification, the Auditor tab for both assessed (real severity caps and caveat now visible) and indeterminate compliance, the CISO tab's real risk score render (`41/100`, not `NaN`), and the garbage-file error path (`results.status === 'error'`). Zero console errors, zero blank pages, across all of them.

### 6.3 `backend/report_generator.py` — unchanged, not touched this session

Still fully hardcoded — string literals baked into the PDF generation code, takes no arguments, cannot reflect a specific analysis. `main.py`'s `/export` endpoint now calls it and returns a real file (§4.1), but the file's *content* is unchanged stub text.

---

## 7. Priority-ordered action list

1. ~~Relaunch Docker Desktop and move its disk image to D:~~ **✅ DONE** — verified healthy, data disk confirmed relocated to `D:\DockerDesktopWSL`.
2. ~~Fix IKE handshake capture ordering~~ **✅ DONE** — verified with a real captured handshake.
3. ~~Fix `ike_parser.py` crypto-field extraction against real traffic~~ **✅ DONE** — real RFC 7296 binary parsing, verified against three distinct real proposal shapes: AEAD (AES-GCM, no integrity transform), CBC+HMAC (AES-CBC/SHA1), and weak/legacy (3DES/SHA1/MODP1024) (§3.2, §5.3.1).
4. ~~Full 8-variant dataset generation~~ **✅ DONE** — 56/56 captures verified real via actual packet counts, not just file size (§3.5). Five distinct bugs found and fixed along the way (transport-mode traffic routing, `bypass-lan`, dead servers after container recreate, IPv6 URL brackets, IPv6-only socket binding) - see §3.4.
5. ~~Retrain the model on real data~~ **✅ DONE** — `models/calibrated_rf_model_real.pkl` trained on 40 real flows from the completed dataset. Result reported honestly, not dressed up: 100% test accuracy on n=8 is a small-sample artifact, not a validated number, and `email` has **zero** real examples (every capture fell below the 20-packet floor). The genuinely meaningful result: a held-out real ICMP capture that the synthetic model still misclassifies as `email` (82% confidence) is now correctly classified as `icmp` (58% confidence) by the real model. See ML pipeline docs/handoff for the full comparison table.
6. ~~Decide on `ml_pipeline/adversarial.py`~~ **✅ DONE** — deleted, confirmed dead first (§6.1).
7. ~~Fix `frontend/Dashboard.jsx`~~ **✅ DONE** — deleted, confirmed dead first (§6.1).
8. ~~Fix `frontend/index.html`~~ **✅ DONE** — all six schema mismatches fixed (§6.2.1) and re-verified live against the running backend, same standard as the original finding: zero console errors, zero blank pages, across every `status` combination `main.py` can send (assessed/indeterminate/unavailable/classified/error). The new `mode_inference` section (§5.4) is real backend data not yet surfaced in the UI at all - a reasonable next addition if you want it visible, not a bug in what's there now.
9. ~~Build Tunnel-vs-Transport mode inference~~ **✅ DONE, honestly** — real ESP payload-length signal, wired into `main.py`'s `mode_inference` section with its actual LOGO-validated reliability (~0.55 balanced accuracy, close to chance) surfaced alongside every prediction, not hidden. See §5.4 for the full empirical finding, including the traffic-type-dependent sign flip (Bulk inverts the direction) that's the real reason a general classifier doesn't work well at this sample size. **If you want this more reliable for the judges, the fix is more real Transport-mode captures** (only 2 exist vs 6 Tunnel), not a better model.
10. **Make `report_generator.py` read real analysis data** instead of hardcoded strings, once you're ready to invest in that (it was explicitly out of scope for the backend-wiring pass).
11. **Address the ISCXVPN2016 claim** — either actually download and replay the real dataset (large download, needs your go-ahead) or relabel every place that number appears (`build_log.md`, PPT deck, any pitch scripts) as synthetic/illustrative.
12. **General: continue freeing up C: drive space** — improved from ~57MB to 3.35GB free after the Docker move, but still tight for a 274GB drive.
