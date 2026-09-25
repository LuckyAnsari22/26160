# SIH 26160: AI-Powered IPsec VPN Protocol Analyzer
## Comprehensive Research & Strategy Dossier

This document compiles all competitive intelligence, cryptographic standards, machine learning architecture justifications, and pitch strategies developed for the 36-hour Grand Finale.

---

## 1. Competitive Intelligence & "The Wedge"

The technical baseline across all top competing teams (e.g., `sentinel-ipsec`, `VaultScope`, `SIH_PS160`) has completely converged on a hybrid architecture: a deterministic cleartext wire parser + a statistical ML flow classifier for ESP.

### What the Competition is Doing:
*   **Explainable AI (SHAP):** Top teams are using SHAP to explain their model's predictions.
*   **Confound Auditing:** Teams like `SIH_PS160` and `VaultScope` explicitly test whether their models accidentally learned the cipher (e.g., block size) instead of the traffic behavior.
*   **Honesty on Accuracy:** The best teams admit that 99% accuracy on a lab dataset is inflated and does not represent real-world performance.

### Your Differentiator (The Wedge): Countermeasure Simulation
Every other team built a surveillance tool (showing what an attacker can see). **You are building a defensive self-audit platform.** 
No competitor has implemented a **Countermeasure Simulation / Leakage Quantification Module**. Your tool actively attacks the captured traffic using your ML model, simulates zero-delay adaptive padding (like the FRONT defense, which has a known 33% bandwidth overhead), and reports exactly how many bytes of MTU padding it takes to blind the AI (e.g., dropping confidence from 98% down to 45%). This is presented as the **"Traffic Analysis Resistance Score."**

---

## 2. Machine Learning Architecture (Why not Deep Learning?)

For classifying flow-level statistical features on a small dataset (a few thousand flows), **Random Forest** mathematically and empirically dominates deep learning. 

**Defending the Choice to Judges:**
1.  **Data Topology:** Neural networks excel at unstructured data (bytes/images). Random Forests have a superior inductive bias for structured, tabular data (flow statistics) because they build hard decision boundaries.
2.  **Overfitting (Data Starvation):** NNs are data-hungry. On a small dataset, an NN will just memorize the training set. Random Forest uses bagging to reduce variance and prevent overfitting, ensuring real-world generalization.
3.  **Explainability:** In cybersecurity, black boxes are liabilities. Random Forests natively integrate with TreeSHAP to calculate exact, local feature attributions, proving *why* a flow was flagged.

### Calibrated Probabilities (Platt Scaling)
Raw Random Forest outputs are not true probabilities (they push toward the center). To report an honest "Confidence Score," use **Platt Scaling** via `scikit-learn`'s `CalibratedClassifierCV(method='sigmoid')`. This maps raw outputs to real-world probabilities, visualizable via a Reliability Diagram (Calibration Curve) hugging the `y=x` diagonal.

---

## 3. Cryptographic Rule Engine (NIST SP 800-77 & RFCs)

Your deterministic rule engine evaluates IKE/ESP configurations using a **Severity Cap Algorithm**. Additive scoring is dangerous in crypto (strong AES + weak MD5 = 0 security). If any component is mathematically broken, the tunnel's score is hard-capped.

### The Rule Matrix
| Parameter | Condition | Rule | Severity / Cap | Source |
| :--- | :--- | :--- | :--- | :--- |
| **IKE Version** | `IKEv1` (esp. Aggressive Mode) | MUST NOT | **CRITICAL (Cap: 25/100)** | NIST SP 800-77. Offline dictionary attack risk. |
| **Weak Ciphers** | `ENCR_DES`, `ENCR_NULL`, `AUTH_MD5` | MUST NOT | **CRITICAL (Cap: 25/100)** | Completely broken cryptography. |
| **Legacy Block** | `ENCR_3DES` | MUST NOT | **HIGH (Cap: 59/100)** | RFC 8221/8247. SWEET32 collision vulnerability. |
| **Weak DH** | `Group < 14` (e.g., Grp 1, 2, 5) | MUST NOT | **HIGH (Cap: 59/100)** | Logjam vulnerability. Provides < 112 bits of security. |
| **Deprecated** | `ENCR_AES_CBC`, `AUTH_SHA1` | MUST- | **MEDIUM (Cap: 79/100)** | Phasing out. CBC is vulnerable to padding oracles; AEAD is preferred. |
| **Modern AEAD** | `AES_GCM_16`, `CHACHA20_POLY1305` | MUST | **PASS** | RFC 8221/8247. |
| **Strong DH** | `Group 14, 19, 31` | MUST | **PASS** | 2048-bit MODP or Curve25519. |

---

## 4. Protocol Visibility Limits (What you can actually see)

You must not overclaim what your tool can parse from a PCAP.
*   **Cleartext (`IKE_SA_INIT`):** IKE version, IKE ciphers, DH groups, Post-Quantum support flags.
*   **Encrypted (`IKE_AUTH` & ESP):** ESP ciphers (AES-GCM vs CBC), Tunnel vs Transport mode, internal traffic payloads. *These must be inferred via ML or read from a gateway config file (`ip xfrm state`).*
*   **Unobservable:** Pre-shared keys (PSKs), exact SA lifetime configs (only elapsed time is visible).

---

## 5. Future-Proofing: Post-Quantum Cryptography (RFC 9370)

You can detect PQC-readiness in 10 lines of code without doing any complex math, giving you a massive "Future-Proof" feature for the judges.

*   **How it works:** Because ML-KEM keys are huge, RFC 9370 adds an `IKE_INTERMEDIATE` phase (Message Type 43) to prevent fragmentation during the initial handshake.
*   **How to detect it:** Parse the cleartext `IKE_SA_INIT` packet. If it contains a **Notify Payload with Type `16438`** (`INTERMEDIATE_EXCHANGE_SUPPORTED`), the endpoint is PQC-ready. If you see Message Type 43, a hybrid key exchange is actively happening.

---

## 6. Testbed & Dataset Generalization

**The Setup:** Use a Docker-compose topology (`Alice ↔ Moon ↔ WAN ↔ Sun ↔ Bob`). Ensure MTU on endpoints is set to ~1360 to prevent ESP encapsulation from causing IP fragmentation, which destroys flow statistics. Use `swanctl.conf`, not the deprecated `ipsec.conf`.

**Proving Generalization:**
Do not just train and test on synthetic lab `ping` traffic. 
1.  Download the **ISCXVPN2016 dataset** (UNB CIC), which contains real PCAPs of Skype (VoIP), Netflix (Video), and Email.
2.  Use `tcprewrite` to map the IPs to your Docker subnet.
3.  Replay the PCAPs through your IPsec tunnel using `tcpreplay`.
4.  Capture the resulting ESP traffic.
Testing your model on this external, real-world data proves to the judges that your ML didn't just memorize your laptop's specific network latency artifacts.

---

## 7. Explainable AI (SHAP) Reporting

Translate raw SHAP arrays into human-readable forensics to prove your tool is built for enterprise security analysts.

*   **Technical Report Example:** "Predicted `CLASS_VOIP` (87%). Driven by `fwd_pkt_len_std` (Impact +0.45). The standard deviation was 2.4 bytes, matching rigid audio codec framing, perfectly isolating this from web/video traffic."
*   **Executive Report Example:** "Unsanctioned VoIP traffic detected. The flow was flagged due to highly consistent, small packet sizes and a steady inter-arrival time matching real-time human speech."

---

## 8. Real-World Citable Incidents
Use these to validate the problem statement on your opening slide:
1.  **Logjam (CVE-2015-4000):** State actors breaking 1024-bit Diffie-Hellman (Group 2).
2.  **SWEET32 (CVE-2016-2183):** 64-bit block cipher collision attacks rendering 3DES completely broken.
3.  **IKEv1 Aggressive Mode:** Exploitation of cleartext identity hashes to perform offline dictionary attacks against weak Pre-Shared Keys (PSKs).

---

## 9. Limitations & Scope Boundaries (The "Hostile Q&A" Shield)

To demonstrate engineering maturity, preempt hostile judging by explicitly acknowledging where the architecture breaks down. Incorporating these into a "Scope & Limitations" slide shows logical, practical judgment over blind technical arrogance.

### Where the Solution Breaks Down

1. **Site-to-Site Multiplexing (The Biggest Gap)**
   * **Limitation:** The testbed evaluates one client to one server (single flow). Real enterprise gateway-to-gateway deployments multiplex dozens of flows into one tunnel. Separating an interleaved VoIP burst from a Video burst is a fundamentally harder problem.
   * **Defense:** "Our current scope handles clean, single-flow/branch-office scenarios. Multiplexed flow disaggregation is future work and is an unsolved problem across all competing SIH repositories."

2. **Tunnel Mode vs. Transport Mode**
   * **Limitation:** In Transport mode, the inner IP header is exposed, making ML classification mostly redundant. 
   * **Defense:** "Our ML metadata classification module specifically targets **Tunnel Mode**, where the inner IP header is hidden, making statistical classification strictly necessary."

3. **Authentication Header (AH) Deployments**
   * **Limitation:** AH provides integrity, not confidentiality. The payload is in cleartext.
   * **Defense:** "If a deployment uses AH, the ML layer is bypassed entirely in favor of simple Deep Packet Inspection (DPI). Our classifier strictly targets ESP payloads."

4. **Short Flows & Pings**
   * **Limitation:** ICMP pings or short control messages lack sufficient packets to build size/timing distributions. 
   * **Defense:** "Our classifier is designed to report honestly low confidence on short flows, rather than forcing a hallucinated guess. A minimum threshold acts as a confidence floor guard."

5. **Capture Point Distortion**
   * **Limitation:** Packet timing (jitter) and sizes (due to fragmentation or NIC offloading like GRO/TSO) change depending on where the PCAP is collected.
   * **Defense:** "This model assumes capture near the VPN gateway. Significant downstream hops will degrade accuracy due to network jitter, a known constraint in all traffic classification models."

6. **Countermeasure (Padding) Limits & Costs**
   * **Limitation:** Padding reduces, but does not completely eliminate, leakage against a highly-resourced adversary. Furthermore, defenses like FRONT incur real bandwidth overhead (e.g., ~33%).
   * **Defense:** "We do not claim to offer a perfect, cost-free guarantee. Our tool provides a risk trade-off: calculating exactly how much bandwidth overhead is required to drop an attacker's confidence from 98% to 45%, raising the adversary's cost."

7. **Rekeying & Perfect Forward Secrecy (PFS)**
   * **Limitation:** Mid-capture session rekeys can contaminate labeled flows if the Security Parameter Index (SPI) changes unexpectedly.
   * **Defense:** "Our protocol parser tracks SPI changes mid-session to ensure statistical bins aren't split or contaminated during PFS rekey events."


---

## 10. Prior Art & Positioning (The "Logical Over Technical" Reframe)

A technically sharp judge will know that parts of this problem have been solved for years. If you claim to have invented protocol parsing or encrypted traffic classification, you will lose credibility instantly. Instead, use prior art to prove your engineering maturity.

### The Existing Tools (What you are NOT inventing)
*   **ike-scan & Wireshark:** Protocol parsing is a solved problem. These tools already extract IKE version, ciphers, and DH groups perfectly. 
*   **SCAP / Nessus / Qualys:** Automated compliance auditing and flagging weak ciphers is already done by standard enterprise vulnerability scanners.
*   **Cisco Encrypted Traffic Analytics (ETA):** This is a massive commercial product deployed since 2017. Cisco ETA already classifies what is inside encrypted traffic (primarily TLS) using the exact metadata you are using (packet sizes and timing) without decrypting anything, boasting 99%+ accuracy.

### The Reframe: Cisco ETA is your Ally, not your Enemy
If a networking-literate judge asks, **"Isn't this just Cisco ETA for IPsec?"** you must answer with this:

> *"Exactly. We are not claiming to have invented encrypted flow classification—Cisco ETA already proved commercially that metadata timing and packet size analysis works at scale. However, Cisco ETA is proprietary, primarily focused on TLS malware detection, and built for the attacker/defender monitoring paradigm.*
> 
> *Our innovation is not the classification itself; it's the application of this validated industry technique to **open-source IPsec** and framing it as a **self-audit tool**. We are answering a question Cisco ETA does not ask: 'How much does my own tunnel leak to an adversary, and exactly how much MTU padding does it take to close that leak?' We are building on the shoulders of ike-scan and ETA to provide a defensive mitigation simulator."*

### Practical Takeaway for the Pitch
Do not hide the existence of ike-scan or Cisco ETA. Put them on a "Prior Art" slide. Tell the judges: *"We aren't reinventing the wheel. We are taking the proven engine of Cisco ETA, combining it with the deterministic parsing of ike-scan, and adding a novel Countermeasure Simulator to solve the problem for the VPN administrator."*

