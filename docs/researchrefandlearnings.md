# PS 26160 — Complete Learning Resource List (Basics → Advanced)

Organized by topic, each roughly ordered easy → hard. Everything here is real and verifiable — no invented links.

---

## 1. Networking & IPsec Fundamentals

**Concepts first:**
- Wikipedia — [Internet Key Exchange](https://en.wikipedia.org/wiki/Internet_Key_Exchange) — quick, accurate overview of IKEv1/IKEv2 history and purpose.
- strongSwan official docs — [Introduction to the IPsec Protocol](https://docs.strongswan.org/docs/6.0/howtos/ipsecProtocol.html) — the best concise technical explanation of ESP, IKEv2, SPI, IKE_SA_INIT — written by the people who maintain the actual software you'll use.
- ipsec.guru — [Chapter 4: IKE Protocol Deep Dive](https://ipsec.guru/chapter4/) — clear breakdown of Phase 1/Phase 2 negotiation with real config examples (Cisco ASA syntax, but concepts transfer directly).

**Video:**
- YouTube — ["IPSEC VPN fundamentals | IKE Phase 1 & 2"](https://www.youtube.com/watch?v=ehGfF2t2uhw) — DH exchange and phase-by-phase tunnel formation, visual and beginner-friendly.
- YouTube — ["IPsec IKEv2: Complete Guide to Negotiation, Tunnel Establishment, and Security"](https://www.youtube.com/watch?v=4dB7siIKLaM) — more advanced, covers deployment nuances.
- YouTube — ["IKEv1 and IPSEC Deep Dive"](https://www.youtube.com/watch?v=LBYoQ0KBEoc) — useful specifically because your PS asks about both IKE versions and you need to explain why IKEv1 Aggressive Mode is a known risk.

**Read the actual RFCs** (yes, really — you'll cite these in your report, so read them once properly instead of only skimming summaries):
- [RFC 4303](https://www.rfc-editor.org/rfc/rfc4303) — ESP, including Traffic Flow Confidentiality padding (your countermeasure's actual spec).
- [RFC 7296](https://www.rfc-editor.org/rfc/rfc7296) — IKEv2 core protocol.
- [RFC 8221](https://www.rfc-editor.org/rfc/rfc8221) / [RFC 8247](https://www.rfc-editor.org/rfc/rfc8247) — algorithm requirements (your compliance rule-engine's backbone).
- [NIST SP 800-77 Rev.1](https://csrc.nist.gov/pubs/sp/800/77/r1/final) — Guide to IPsec VPNs.

---

## 2. Building the Testbed (strongSwan)

- computingforgeeks.com — ["Configure Site-to-Site VPN using strongSwan on Ubuntu"](https://computingforgeeks.com/configure-site-to-site-vpn-using-strongswan-on-ubuntu/) — full walkthrough, widely used and kept up to date.
- oneuptime.com — ["How to Configure IPsec Site-to-Site VPN on Linux with strongSwan"](https://oneuptime.com/blog/post/2026-03-20-ipsec-site-to-site-linux-strongswan/markdown) — production-style config with real `ipsec.conf` syntax, recent (2026).
- zenarmor.com — ["How to configure IPsec site to site VPN tunnel on Ubuntu"](https://www.zenarmor.com/docs/network-security-tutorials/how-to-configure-ipsec-site-to-site-vpn-tunnel-on-ubuntu) — good if you're building on VirtualBox VMs specifically, which is likely for a hackathon testbed.
- **GitHub**: search `strongswan docker testbed` — several community Docker Compose setups exist for spinning up multi-node IPsec labs quickly; verify against the official [strongSwan GitHub repo](https://github.com/strongswan/strongswan) for anything you're unsure about.

---

## 3. Packet Capture & Manipulation (Wireshark, tcpdump, Scapy)

- Official Scapy docs & GitHub — [github.com/secdev/scapy](https://github.com/secdev/scapy) — the canonical source; the README alone gets you sending/sniffing packets in 10 minutes.
- PyPI — [scapy project page](https://pypi.org/project/scapy/) — install instructions and a short usable example.
- GitHub — [yungshenglu/Packet_Manipulation](https://github.com/yungshenglu/Packet_Manipulation) — a real university networking-course lab: define a protocol in Scapy, send/sniff it, then analyze the capture in Wireshark. Good hands-on structure to imitate for your own IKE/ESP parsing code.
- Wireshark's own IKE/ESP dissectors are your reference implementation for what "correct" cleartext field parsing looks like — capture your own testbed traffic and compare your parser's output field-by-field against what Wireshark shows.

---

## 4. Encrypted Traffic Classification (the core ML problem)

**Foundational paper (read this first, it's short and directly cited by every competing team):**
- Gil, Lashkari, Mamun, Ghorbani (2016) — *"Characterization of Encrypted and VPN Traffic Using Time-Related Features,"* ICISSP 2016. Search the title on Google Scholar or ResearchGate for a free PDF — this defines the SPLT (Sequence of Packet Lengths and Times) feature methodology almost every SIH team is using, including yours.

**Dataset:**
- UNB Canadian Institute for Cybersecurity — [ISCXVPN2016 dataset](https://www.unb.ca/cic/datasets/vpn.html) — the standard public VPN/non-VPN traffic dataset, useful to test whether your model generalizes beyond your own lab captures.

**Hands-on tutorials:**
- GitHub — [FlowFrontiers/ml-flow-class-tutorial](https://github.com/FlowFrontiers/ml-flow-class-tutorial) — genuinely excellent, recent, end-to-end Jupyter notebooks covering flow metering → feature engineering → model training → explainability for encrypted traffic classification. This is close to a direct blueprint for your ML pipeline.
- GitHub — [qa276390/Encrypted_Traffic_Classification](https://github.com/qa276390/Encrypted_Traffic_Classification) — compares Random Forest, DNN, CNN, autoencoders on the same problem; useful for justifying your model choice with real comparative numbers.
- GitHub — [CESNET/WIF](https://github.com/CESNET/WIF) (Weak Indication Framework) — a production-grade C++ library for encrypted traffic analysis with scikit-learn ML integration; more advanced, useful if you want to see how a "real" implementation structures classifiers/combinators.

---

## 5. Model Explainability (SHAP)

- Official SHAP documentation — [shap.readthedocs.io](https://shap.readthedocs.io/) — the canonical reference.
- Official SHAP GitHub — [github.com/shap/shap](https://github.com/shap/shap) — README has copy-pasteable `TreeExplainer` examples for Random Forest, which is exactly what you need for Slide 8's waterfall chart.
- Practical lab walkthrough (PDF) — Politecnico di Torino's ["Lab 3b: SHAP"](https://dbdmg.polito.it/dbdmg_web/wp-content/uploads/2026/04/Lab3b_Local_explanation_methods_SHAP_sol.pdf) — a full worked example training a Random Forest then explaining it with SHAP, step by step.

---

## 6. Confidence Calibration (Platt Scaling)

- scikit-learn official docs — [Probability calibration](https://scikit-learn.org/stable/modules/calibration.html) — covers `CalibratedClassifierCV` directly, exactly what your "AI Confidence Score" needs to be mathematically honest.
- scikit-learn official docs — [RandomForestClassifier](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html) reference, for the base model you're calibrating.

---

## 7. Traffic-Analysis Countermeasures (padding/leakage — your innovation wedge)

**The core paper your countermeasure simulator is based on:**
- Juárez, Imani, Perry, Diaz, Wright (2016) — *"Toward an Efficient Website Fingerprinting Defense"* (WTF-PAD), ESORICS 2016 — [free PDF via nymity.ch](https://nymity.ch/tor-dns/bibliography/pdf/Juarez2016a.pdf). This is the paper behind your "91%→20% accuracy drop" citation — read it fully, not just the abstract, since a technical judge could ask about its actual mechanism.
- Blog explainer — [cs.kau.se "thebasketcase" WTF-PAD writeup](https://www.cs.kau.se/pulls/hot/thebasketcase-wtfpad/) — a much more digestible explanation of the adaptive-padding state machine than the paper alone, good for actually understanding it before implementing a simplified version.

**Important honesty check — read this before overclaiming your countermeasure's effectiveness:**
- Barman, Siby, Wood, Fayed, Sullivan, Troncoso — *"This is not the padding you are looking for! On the ineffectiveness of QUIC PADDING against website fingerprinting"* — [Cloudflare Research PDF](https://files.research.cloudflare.com/publication/Barman2022.pdf). This paper shows network-layer padding alone has real, published limits against strong adversaries — cite this specifically when a judge asks "does your countermeasure fully solve leakage" so your answer is grounded, not overclaiming.
- FRONT/GLUE defense poster — [IEEE S&P 2019 poster PDF](https://www.ieee-security.org/TC/SP2019/posters/hotcrp_sp19posters-final6.pdf) — shows more modern, lower-overhead alternatives to WTF-PAD if you want to go beyond the basic approach.
- Real-world commercial deployment example — Mullvad VPN's "DAITA" (Defense Against AI-guided Traffic Analysis) is a shipped, real-world implementation of these exact padding-defense ideas in a production VPN — worth mentioning as proof this isn't purely academic.

---

## 8. Prior Art You Must Know Cold

- `ike-scan` — [GitHub: royhills/ike-scan](https://github.com/royhills/ike-scan) — the actual tool; read its README to know exactly what it fingerprints so you never present protocol-ID as your innovation.
- Cisco's own material on Encrypted Traffic Analytics (ETA) — search "Cisco Encrypted Traffic Analytics white paper" on cisco.com for their official technical explanation of how they classify traffic from metadata without decryption — read this so you can accurately describe (and differentiate from) it in Q&A.

---

## 9. General Cybersecurity/Networking Refresher (if anyone on the team needs the basics)

- Professor Messer's free [Network+ and Security+ video courses](https://www.professormesser.com/) on YouTube — thorough, free, widely used for foundational networking and security concepts if someone on your team needs to get up to speed quickly.
- freeCodeCamp YouTube channel has multiple full-length (several-hour) free courses on "Network Security," "Ethical Hacking," and "Machine Learning" — search their channel directly for the most current version, since these get re-uploaded/updated periodically.

---

## How to actually use this list under time pressure

1. Don't read everything before starting to build — read Section 1 + skim Section 4's foundational paper first, then start the testbed (Section 2) while reading Sections 5-7 in parallel as you need them.
2. The WTF-PAD paper (Section 7) and the Cloudflare "ineffectiveness of padding" paper together are your single most important reading pair — they're what let you make an honest, technically defensible claim about your core innovation instead of an overclaimed one.
3. Bookmark the RFCs — you'll reference specific sections of them repeatedly across your technical report, rule engine, and Q&A prep.
 Yes. **If the rubric explicitly says “Details / Links of the reference and research work,” your current references slide is not quite sufficient yet.** It has the details, but the links are not actually visible/clickable.

I’d fix the last slide by keeping it clean and adding a **small “Open Sources” footer / QR area**, rather than putting ugly raw URLs beside every citation.

### What should be linked

**[1] Traffic-analysis research**
Draper-Gil et al., *Characterization of Encrypted and VPN Traffic Using Time-related Features*, ICISSP 2016, pp. 407–414, DOI 10.5220/0005740704070414. The paper specifically studies flow/time-based features for encrypted/VPN traffic characterization. ([scitepress.org][1])
[Paper / DOI](https://doi.org/10.5220/0005740704070414?utm_source=chatgpt.com)

**[2] Padding / traffic-analysis defense**
Juárez et al., *Toward an Efficient Website Fingerprinting Defense (WTF-PAD)*, ESORICS 2016.

**[3] Countermeasure limitations**
Barman et al., *This is not the padding you are looking for!* — Cloudflare Research, 2022. This is particularly useful because it supports your **honest limitation** that padding does not guarantee resistance to traffic analysis. ([research.cloudflare.com][2])
[Cloudflare Research paper](https://research.cloudflare.com/barman2022/?utm_source=chatgpt.com)

---

### Standards / Protocols

**[4] RFC 4303 — ESP**
Defines IP Encapsulating Security Payload and includes limited traffic-flow confidentiality. ([RFC Editor][3])
[RFC 4303](https://www.rfc-editor.org/info/rfc4303?utm_source=chatgpt.com)

**[5] RFC 7296 — IKEv2**
Core IKEv2 specification for establishing and maintaining IPsec Security Associations. ([RFC Editor][4])
[RFC 7296](https://www.rfc-editor.org/info/rfc7296?utm_source=chatgpt.com)

**[6] RFC 8221 / RFC 8247 — Cryptographic requirements**
Algorithm guidance for ESP/AH and IKEv2. ([RFC Editor][5])
[RFC 8221](https://www.rfc-editor.org/info/rfc8221?utm_source=chatgpt.com)
[RFC 8247](https://www.rfc-editor.org/info/rfc8247?utm_source=chatgpt.com)

**[7] RFC 9370 — Multiple Key Exchanges / PQ readiness** ([RFC Editor][6])
[RFC 9370](https://www.rfc-editor.org/info/rfc9370?utm_source=chatgpt.com)

**[8] NIST SP 800-77 Rev. 1 — Guide to IPsec VPNs**
This should absolutely be one of your most prominent references because your compliance engine is explicitly NIST-aligned. NIST describes it as practical guidance for implementing IPsec/IKE and mitigating associated risks. ([NIST][7])
[NIST SP 800-77 Rev. 1](https://csrc.nist.gov/pubs/sp/800/77/r1/final?utm_source=chatgpt.com)

**[9] NIST SP 800-30 — Risk Assessment**

---

### Dataset

**[10] ISCXVPN2016 — UNB Canadian Institute for Cybersecurity**

This one definitely needs a link. The UNB page provides the VPN/non-VPN dataset, PCAP/CSV availability, traffic categories and the associated 2016 paper. 

[ISCXVPN2016 Dataset — UNB CIC](https://www.unb.ca/cic/datasets/vpn.html?utm_source=chatgpt.com)

---

### Prior Art

**[11] ike-scan**
[ike-scan — GitHub](https://github.com/royhills/ike-scan?utm_source=chatgpt.com)

**[12] Cisco Encrypted Traffic Analytics (ETA)**
For this one, use Cisco's official product/research page rather than a random third-party article.

---

### Indian regulatory context

**[13] Digital Personal Data Protection Act, 2023**
The official India Code record identifies the Act as Act No. 22 of 2023. ([India Code][8])
[DPDP Act 2023 — India Code](https://www.indiacode.nic.in/indiacode/handle/123456789/22037?view_type=browse&utm_source=chatgpt.com)

**[14] CERT-In Directions under Section 70B**
Use the official CERT-In page. It hosts the April 28, 2022 directions and related FAQs/updates. ([CERT-In][9])
[CERT-In Directions 70B](https://cert-in.org.in/Directions70B.jsp?utm_source=chatgpt.com)

---

# How I'd change your actual slide

Don't turn it into:

> `[1] ... https://...`
> `[2] ... https://...`

That will destroy the beautiful design you've built.

Instead, keep your current **5-category reference layout**, and add a thin footer:

### **SOURCE LIBRARY**

`[01] Research` · `[02] Standards` · `[03] Dataset` · `[04] Prior Art` · `[05] Regulation`

Then put **two QR codes** at the bottom-right:

**RESEARCH + STANDARDS**
**DATASET + REGULATION**

And underneath:

> **Full clickable bibliography available in project documentation**

That satisfies the **“details / links”** requirement without making the presentation unreadable.

### One more important correction

Your current slide labels RFC 8221/8247 together as:

> “Cryptographic Algorithm Requirements for ESP/AH and IKEv2.”

That's broadly fine, but they are **two separate RFCs with different scopes**: RFC 8221 covers ESP/AH, while RFC 8247 covers IKEv2 algorithm implementation requirements/guidance. ([RFC Editor][5])

For a cybersecurity judging panel, I'd keep them separated in the final bibliography.

**So: your reference slide has the right research foundation, but adding an actual source-access mechanism is what turns it into a complete “Details / Links” slide.**

[1]: https://www.scitepress.org/PublishedPapers/2016/57407/?utm_source=chatgpt.com "SCITEPRESS - SCIENCE AND TECHNOLOGY PUBLICATIONS"
[2]: https://research.cloudflare.com/barman2022/?utm_source=chatgpt.com "Blog | Cloudflare Research"
[3]: https://www.rfc-editor.org/info/rfc4303/?utm_source=chatgpt.com "RFC 4303: IP Encapsulating Security Payload (ESP) | RFC Editor"
[4]: https://www.rfc-editor.org/info/rfc7296/?utm_source=chatgpt.com "RFC 7296: Internet Key Exchange Protocol Version 2 (IKEv2) | RFC Editor"
[5]: https://www.rfc-editor.org/info/rfc8221/?utm_source=chatgpt.com "RFC 8221: Cryptographic Algorithm Implementation Requirements and Usage Guidance for Encapsulating Security Payload (ESP) and Authentication Header (AH) | RFC Editor"
[6]: https://www.rfc-editor.org/info/rfc9370/?utm_source=chatgpt.com "RFC 9370: Multiple Key Exchanges in the Internet Key Exchange Protocol Version 2 (IKEv2) | RFC Editor"
[7]: https://www.nist.gov/publications/guide-ipsec-vpns?utm_source=chatgpt.com "Guide to IPsec VPNs | NIST"
[8]: https://www.indiacode.nic.in/indiacode/handle/123456789/22037?view_type=browse&utm_source=chatgpt.com "India Code: Digital Personal Data Protection Act, 2023."
[9]: https://cert-in.org.in/Directions70B.jsp?utm_source=chatgpt.com "Cert-In - Directions70B"
