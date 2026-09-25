# SLIDE 4: Feasibility, Challenges & Mitigation Strategies

### Feasibility

- Deterministic parsing (Tier 1) is low-risk — direct field extraction, no ML uncertainty. **[STRUCTURAL]**
- ML classification (Tier 2) is feasible within team/time constraints using classical ML (Random Forest) on hand-crafted features — proven approach with modest data requirements, unlike deep learning which needs far more labeled data than a hackathon timeline allows.
- Deployment is **out-of-band** (passive SPAN tap) — zero risk of disrupting live network traffic, which also makes pilot deployment low-friction to approve.

### Challenges & Risks → Mitigation (paired directly)

| Challenge / RiskMitigation                                                      |                                                                                                                                                                    |
| ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Short flows (ICMP, brief control messages) give unreliable classification       | Hard 20-packet minimum floor — below it, flagged `Indeterminate` instead of forced-guessed **[STRUCTURAL]**                                                        |
| NIC hardware offloading (GRO/TSO) and WAN jitter distort packet-size signatures | 7-day "Observation Mode" baseline period before live alerting activates                                                                                            |
| Site-to-Site tunnels multiplex many users into one SA — flows interleave        | Explicitly scoped to Client-to-Gateway topology for this prototype; multiplexed separation named as future work, not oversold as solved                            |
| False sense of security if leakage score is misread as "total protection"       | Metric explicitly labeled "Passive Side-Channel Resistance," not "overall security"; documentation states padding raises attacker cost, doesn't guarantee immunity |
| Alert fatigue from false positives eroding analyst trust                        | High Platt-calibrated confidence threshold (>90%) before any SIEM alert fires — trading recall for precision deliberately                                          |
| Dual-use concern: traffic classification repurposed for surveillance            | Scoped to broad security categories only (not granular app fingerprinting); designed for authorized self-audit with RBAC + audit logging                           |

**Visual concept — "Shield Rings"** (not a plain risk table): Draw a set of 3-4 concentric shield/ring arcs around a small central icon of the IPsec tunnel — each ring labeled with one risk it "blocks," moving from innermost (technical risks like short-flow floor) to outermost (operational/trust risks like alert fatigue and dual-use). This "defense-in-depth" visual metaphor directly demonstrates layered honesty about risk rather than a flat table, and visually reinforces the "shield" framing from your elevator pitch.

---
 Yes — **the three required judging criteria are covered**, but I would make **two technical corrections** before calling the slide final. The current generated slide is visually strong, but the content can be made more rigorous.

### Coverage against the PS

| Requirement                      | Coverage    | Where                                           |
| -------------------------------- | ----------- | ----------------------------------------------- |
| **Analysis of feasibility**      | ✅ Strong    | Left “FEASIBILITY” panel                        |
| Technical feasibility            | ✅           | Deterministic parsing + Random Forest           |
| Data feasibility                 | ✅           | Hand-crafted features + modest data requirement |
| Deployment feasibility           | ✅           | Passive SPAN / out-of-band architecture         |
| Time/resource feasibility        | ✅           | Classical ML rather than deep learning          |
| **Potential challenges & risks** | ✅ Strong    | Right-side challenge cards + shield layers      |
| Short-flow problem               | ✅           | 20-packet floor                                 |
| GRO/TSO + jitter                 | ✅           | Observation Mode                                |
| Multiplexed tunnels              | ✅           | Explicit prototype scope                        |
| False security interpretation    | ✅           | “Passive Side-Channel Resistance”               |
| Alert fatigue                    | ✅           | Calibrated confidence threshold                 |
| Dual-use/surveillance risk       | ✅           | Scope + RBAC + audit logging                    |
| **Mitigation strategies**        | ✅ Excellent | Every challenge has a paired mitigation         |
| Scope limitations                | ✅           | Explicitly acknowledged                         |
| Operational safeguards           | ✅           | Observation Mode + alert threshold              |
| Ethical safeguards               | ✅           | Authorized self-audit + RBAC/audit logs         |

### The strongest part

The **challenge → mitigation pairing** is exactly what you want.

Instead of saying:

> “There may be false positives.”

you say:

> **False positives → calibrated confidence threshold → alert only above threshold.**

Instead of:

> “Multiplexing is difficult.”

you say:

> **Multiplexing → explicitly constrain prototype to Client-to-Gateway → future work.**

That makes the slide demonstrate **engineering maturity**, not just optimism.

---

## Two changes I'd make

### 1. Don't say “zero risk”

Your current feasibility section says:

> “Zero risk of disrupting live network traffic.”

I'd change that to:

> **No inline modification or forwarding dependency**

or:

> **Passive capture minimizes deployment risk**

Because a SPAN/tap architecture is designed to be non-intrusive, but saying **zero risk** is unnecessarily absolute.

### 2. Be careful with the `>90%` threshold

If you haven't actually validated that threshold experimentally, don't present **>90%** as an established optimal value.

Use:

> **High calibrated-confidence threshold**

until you've tested it.

Then, after validation, you can show:

> **Alert threshold: ≥ X%**

based on your actual precision/recall analysis.

---

# One thing I'd add for a truly high-level feasibility analysis

Your current slide covers **technical feasibility**, but feasibility has another dimension:

### **RESOURCE FEASIBILITY**

You could add a tiny strip:

**Compute:** Standard x86 Linux / cloud VM
**Software:** Open-source stack
**Deployment:** Passive SPAN
**Model:** Classical ML
**Data:** Lab-generated + public replay dataset

This answers the judge's implicit question:

> **“Can a student team realistically build and demonstrate this?”**

And the answer is visually evident.

---

# The final structure I'd use

### LEFT

## **CAN WE BUILD IT?**

Technical + data + deployment + resource feasibility

### CENTER

## **WHAT CAN GO WRONG?**

Layered risk model

### RIGHT

## **HOW DO WE CONTAIN IT?**

Challenge → mitigation pairs

And at the bottom:

> **Feasible because we deliberately constrain what we promise, what we observe, and what we automate.**

That's a much more mature message than simply saying *“Technically feasible.”*

So: **yes, the slide covers all three requested criteria at a strong level.** With those two wording fixes and the small resource-feasibility addition, I'd consider it presentation-ready.
