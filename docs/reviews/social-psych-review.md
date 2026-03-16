# Social Psychology Review: CYT-NG

**Reviewer perspective:** Social psychologist with focus on interpersonal violence, technology-facilitated abuse, and the psychological effects of surveillance and counter-surveillance.

**Date:** 2026-03-16

**Scope:** Review of CYT-NG project documentation including system architecture, spectrum expansion roadmap, base station implementation, and ESP32 handheld hardware plans.

---

## 1. Psychological Impact on Users

### 1.1 Hypervigilance and Ambient Anxiety

CYT-NG is, by design, a system that asks the user to remain attentive to the possibility that they are being watched. The base station architecture monitors nine scanner types simultaneously. The handheld unit is designed for 13+ hours of continuous operation. This is a tool built for persistent, always-on vigilance.

The psychological literature on hypervigilance is clear: sustained threat-monitoring is cognitively expensive and emotionally corrosive. Individuals who maintain a heightened state of alertness over days or weeks reliably develop increased baseline anxiety, disrupted sleep, difficulty concentrating, and a lowered threshold for interpreting ambiguous stimuli as threatening (Kimble et al., 2013; Hypervigilance in PTSD, Clinical Psychology Review). For stalking victims, many of whom already present with PTSD symptomatology, CYT-NG risks amplifying a pre-existing hypervigilant state by giving it a technological scaffold.

The critical distinction is between *informed awareness* and *compulsive monitoring*. A tool that helps a user check their environment once per day and provides a clear summary operates differently from one that streams continuous alerts. CYT-NG's current architecture leans toward the latter model -- continuous scanning, real-time alerts, always-on detection.

**Recommendation:** Introduce a "Daily Summary" mode as the default, where the system collects data silently and presents a consolidated report at a user-chosen time. Reserve continuous real-time alerting for users who explicitly opt in with an acknowledgment that persistent monitoring can increase anxiety. The system should periodically remind users that it is normal for many devices to appear in proximity and that most detections are benign.

### 1.2 The False Positive Problem

This is the most psychologically consequential design issue in the project.

The persistence scoring system (0.0 to 1.0) is a probability estimate, not a binary determination. A score of 0.5 means the system is uncertain. But the user's emotional system does not process uncertainty well under threat conditions. Research on threat perception consistently shows that ambiguous threat information is processed as if it were confirmed threat information -- the brain errs on the side of caution (LeDoux, 1996; Blanchette & Richards, 2010).

Consider: a stalking victim receives a notification that a BLE device has been near them across two locations with a persistence score of 0.4. The *intended* message is "this is probably nothing." The *received* message is "something might be following me." For someone already traumatized, this is indistinguishable from confirmation. Each false positive reinforces the subjective experience of being surveilled, deepens anxiety, and may lead to behavioral changes (avoiding locations, isolating socially, confronting innocent strangers) that are harmful regardless of whether actual surveillance is occurring.

The TPMS detection feature is particularly prone to this. Vehicles in urban environments share routes, parking garages, and neighborhoods. A neighbor's car will naturally produce high persistence scores simply because it is parked near the user's home and commutes similar routes. The documentation acknowledges this for LoRa nodes ("most Meshtastic nodes are stationary routers") but does not address the emotional cost of TPMS false positives with equal seriousness.

**Recommendation:** False positive rates should be treated as a first-class design constraint, not merely an accuracy metric. The system should:
- Suppress alerts below a configurable confidence threshold (default 0.7 or higher).
- Require multi-source corroboration before surfacing an alert to the user (e.g., the same entity detected on both WiFi and BLE, or across three or more distinct locations).
- Present the first detection as informational context ("Device log updated") rather than as an alert.
- Never use the word "surveillance" or "following" for scores below 0.8.

### 1.3 The Emotional Impact of Confirmed Surveillance

True positives present a different but equally serious psychological challenge. Having a suspicion validated by a technical system is a complex emotional event: relief at being believed, terror at confirmation, urgency to act, and potential re-traumatization.

The current design produces technical outputs -- persistence scores, device IDs, KML visualizations. These are forensic artifacts, not emotional support. A user who discovers at 11 PM that a specific Bluetooth tracker has been following them across four locations over the past week needs more than a red marker on a Google Earth map.

**Recommendation:** When the system produces a high-confidence detection (score >= 0.8), it should:
- Present the finding clearly and factually.
- Immediately surface relevant safety resources (see Section 4).
- Include explicit guidance: "This information may be useful if you choose to contact law enforcement or a domestic violence advocate. You do not need to act on this immediately."
- Offer to export the evidence in a format suitable for a legal proceeding or a conversation with a victim advocate.

### 1.4 Design Mitigations for Negative Psychological Effects

The tool should adopt principles from trauma-informed design:

- **User control over information flow.** Let the user decide when they receive alerts, how detailed those alerts are, and what confidence threshold triggers notification. Never surprise the user with a high-severity alert without giving them control over the delivery context.
- **Normalization of benign detections.** The default view should show how many devices were detected AND how many were classified as routine. "247 devices seen today. 246 classified as routine neighborhood traffic. 1 flagged for review." This frames the environment as mostly safe, which is almost always true.
- **Explicit uncertainty communication.** Never present probabilistic findings as binary. "Uncertain" should be a visible, first-class category in the UI, not something the user has to infer from a decimal score.
- **Session limits.** Offer the user a way to schedule monitoring sessions rather than running continuously. "Monitor my commute from 7:30-8:15 AM" rather than "monitor everything always."

---

## 2. Dual-Use Concerns

### 2.1 Offensive Use Cases

CYT-NG is designed to detect surveillance, but several of its capabilities are straightforwardly useful for conducting surveillance:

- **WiFi probe request capture** reveals the SSIDs a target device has connected to, which discloses home networks, workplaces, hotels, and other locations. This is the same data that stalkers, private investigators, and intelligence agencies use for target profiling.
- **BLE tracker detection** identifies the presence and type of Bluetooth devices near the sensor. If deployed covertly near a target's home or workplace, it creates a log of which devices (and by inference, which people) are present at what times.
- **TPMS monitoring** can identify and track specific vehicles by their tire pressure sensor IDs -- unique, persistent, and broadcast constantly. A CYT-NG base station near a parking lot becomes a passive vehicle surveillance system.
- **LoRa/Meshtastic monitoring** reveals node IDs of nearby mesh network users and, if they are on the default channel, their GPS coordinates.
- **ADS-B aircraft tracking** is less of a concern (this data is already publicly available via FlightRadar24, ADS-B Exchange, etc.).
- **The handheld unit** is a portable, concealable surveillance device. The documentation describes it as a personal safety tool, but its capabilities -- WiFi probe capture, BLE scanning, LoRa monitoring, GPS logging, 13+ hour battery life, $58 cost -- also describe an effective covert surveillance platform.

This is not a theoretical concern. In domestic abuse contexts, technology-facilitated stalking is common and escalating. The National Network to End Domestic Violence's annual tech safety survey consistently finds that abusers adopt new surveillance technologies rapidly. A $58 device that passively logs nearby wireless devices and tags them with GPS coordinates would be of immediate utility to an abuser.

### 2.2 Current Design Safeguards

The project documentation contains no discussion of anti-misuse measures. The disclaimer in the README ("intended for legitimate security research, network administration, and personal safety purposes") is a legal fig leaf with no technical enforcement.

### 2.3 Recommended Safeguards

No technical measure can fully prevent misuse of a passive RF receiver. However, the project should implement friction that makes offensive use harder and signals clear normative intent:

- **Self-only monitoring mode as default.** The system should be configured, by default, to detect devices that appear to be following *the user's own device/location* across multiple of *the user's own locations*. This is the surveillance detection use case. The alternative -- sitting in one place and logging all devices that pass by -- is the surveillance use case. These are architecturally distinct, and the system should make the protective use case the path of least resistance.
- **No raw data export by default.** The system currently exports CSV files with MAC addresses, SSIDs, and GPS coordinates. This is a surveillance database. Raw data export should require an explicit "forensic export" action, should be logged, and should include a watermark or metadata tag identifying the exporting device.
- **Decay and deletion.** Device sighting data that has not been flagged as suspicious should be automatically deleted after a configurable retention period (default: 48 hours). Surveillance tools are more dangerous when they accumulate data; counter-surveillance tools should be designed to forget.
- **Ethical use statement at first run.** Not a click-through EULA, but a substantive statement explaining the tool's intended use case and the legal consequences of using passive RF monitoring to stalk, harass, or surveil others. This should be displayed at first launch and stored in the session log.

---

## 3. Power Dynamics

### 3.1 Domestic Abuse Context

Stalking and domestic abuse are characterized by asymmetric power. The abuser typically has more resources, more access, and more willingness to use technology offensively than the victim has capacity to use it defensively. Any tool designed for victims must account for this asymmetry.

Key dynamics:

- **The abuser may have physical access to the victim's devices and home.** In cohabitation situations, the abuser may discover CYT-NG on a shared computer, see the handheld device, or notice the base station's antennas. Discovery of a counter-surveillance tool can escalate violence. Research on technology-facilitated abuse consistently identifies "discovery of protective measures" as a high-risk event (Freed et al., 2017, "Digital Technologies and Intimate Partner Violence," CHI).
- **The abuser may be technically sophisticated.** The current CYT-NG documentation assumes a technically competent user who can compile ESP32 firmware, configure Kismet, and interpret persistence scores. In many domestic abuse situations, the abuser is the more technically skilled partner and may be the one who discovers and repurposes the tool.
- **Financial control** is a common abuse tactic. The $58 handheld is inexpensive, but in a financially controlled relationship, any unexplained purchase is a risk.

### 3.2 Stealth Mode vs. Visible Deterrent Mode

The project should offer both operational modes, but the implications of each are different:

**Stealth Mode (covert operation):**
- No visible UI during operation (screen off, or disguised as another app/device).
- Silent alerts (vibration only, or deferred to a trusted contact).
- Data stored encrypted with a separate password.
- The handheld should be physically inconspicuous (no visible antennas in stealth configuration).
- Rationale: victims in active danger need to gather evidence without alerting the abuser.

**Visible Deterrent Mode:**
- Visible "monitoring active" indicator.
- The device's presence signals to a potential surveillant that they may be detected.
- Useful in post-separation contexts where the victim has physical safety but wants to deter approach.
- Rationale: deterrence is psychologically preferable to detection because it prevents the threatening event rather than merely recording it.

**Recommendation:** Stealth mode should be available but should require explicit activation and should display a safety planning prompt: "If you are in an unsafe situation, consider contacting [resource] before beginning covert monitoring. Discovery of this tool by an abuser can escalate danger." The system should never be in a state where it can be casually discovered by someone browsing the user's files or devices.

### 3.3 Data Security Under Coercion

If an abuser discovers CYT-NG, they may demand access to its data. The system should support:

- **Encrypted storage** with a password separate from the device's login credentials.
- **Plausible deniability** -- a "duress password" that opens a benign-looking dataset or factory-resets the device.
- **Remote wipe** capability if the user has a trusted contact who can trigger deletion.
- **No persistent desktop shortcuts, process names, or file paths** that reveal the tool's purpose. "cyt_gui.py" and "surveillance_analyzer.py" are self-documenting filenames that immediately reveal intent. Consider aliased or obfuscated names in stealth mode.

---

## 4. Community and Support

### 4.1 Resource Integration

CYT-NG should connect users to existing support infrastructure. The tool should include, at minimum:

- **National Domestic Violence Hotline:** 1-800-799-7233 (US) / thehotline.org
- **NNEDV Safety Net project** (technology safety for survivors): techsafety.org
- **Local law enforcement non-emergency numbers** (configurable by the user).
- **RAINN** (Rape, Abuse & Incest National Network): 1-800-656-4673
- **Crisis Text Line:** Text HOME to 741741

These should be accessible from within the application at all times, not only when an alert fires. The resources page should be reachable in two taps/clicks or fewer.

### 4.2 Community Features: Risks Outweigh Benefits

A community feature (forum, shared detection data, mutual support network) creates serious risks:

- **Abusers could join the community** to identify victims, learn counter-counter-surveillance techniques, or socially engineer access to victims' data.
- **Shared detection data** could deanonymize users by revealing their locations and movement patterns.
- **Forum dynamics** can amplify paranoia. Online communities organized around threat detection reliably develop norms that reinforce threat perception and punish expressions of doubt. The social psychology of group polarization (Moscovici & Zavalloni, 1969) predicts that a community of people who believe they are being surveilled will, over time, converge on increasingly extreme beliefs about the prevalence and severity of surveillance.
- **False consensus effects** will lead users to interpret each other's false positives as corroborating evidence.

**Recommendation:** Do not build community features. Instead, provide curated links to existing, professionally moderated support communities (NNEDV forums, local DV organizations). If any data sharing is implemented (e.g., anonymized detection signatures of known tracker devices), it should be one-directional (user contributes to a central database) with no social interaction layer.

### 4.3 Empowerment vs. Vigilantism

The tool should empower users to make informed decisions about their safety. It should not encourage users to:

- Confront suspected surveillants directly.
- Conduct their own counter-surveillance operations beyond passive monitoring.
- Attempt to identify the owner of a detected device.
- Follow or approach a suspected surveillance drone or vehicle.

The documentation's `--stalking-only` flag and the focus on "detecting following behavior" are appropriately scoped. The system should maintain this scope: detect, document, and refer. It should never suggest that the user take direct action against a suspected threat.

**Recommendation:** Include a clear statement in the alert flow: "This tool provides information for your awareness and for sharing with professionals. It is not a substitute for a safety plan developed with a domestic violence advocate or law enforcement."

---

## 5. Alert Communication

### 5.1 Language Matters

The difference between "Device X has been near you for 20 minutes" and "WARNING: You are being followed" is the difference between information and accusation. The first presents a fact. The second assigns intent, triggers a fear response, and demands immediate action.

The current system uses language like "surveillance detection," "stalking-only mode," and "persistence scoring." These are appropriate for the developer audience but must be carefully managed in user-facing communications.

Proposed alert language framework:

| Persistence Score | Internal Classification | User-Facing Language |
|---|---|---|
| 0.0 - 0.3 | Routine | No alert. Logged silently. |
| 0.3 - 0.5 | Noted | No alert. Available in daily summary as "Devices seen at multiple locations" with count only. |
| 0.5 - 0.7 | Elevated | "A device was detected near you at [N] locations over [time period]. This may be coincidental. Tap for details." |
| 0.7 - 0.85 | Significant | "A device has appeared near you at [N] locations over [time period]. You may want to review the details and consider your safety plan." |
| 0.85 - 1.0 | Critical | "A device has been consistently detected near you across [N] locations over [time period]. This pattern is unusual. [View details] [Safety resources] [Export for reporting]" |

Key principles:
- **No exclamation points.** Ever. Calm, factual language only.
- **No speculative intent attribution.** "This pattern is unusual" rather than "you are being followed."
- **Graduated urgency.** The system should not scream at a 0.5.
- **Action options, not action demands.** Present choices, not imperatives.
- **Never use the word "WARNING" or "ALERT" in red text** for sub-critical detections.

### 5.2 Communicating Uncertainty

Persistence scores are probabilities. Users generally do not reason well about probabilities, especially under stress. The system should translate scores into natural language categories rather than presenting raw numbers:

- Do not show "Persistence: 0.73" to the user. Show "Confidence: Moderate" or use a three-level system (Low / Moderate / High).
- If a numerical score is shown (for advanced users), accompany it with context: "This score means the device's pattern of appearances is moderately consistent with following behavior, but could also be explained by shared commute routes or neighborhood proximity."
- The multi-source corroboration data is useful context: "This device was detected on WiFi only" is less alarming than "This device was detected on WiFi, BLE, and its vehicle's tire pressure sensors were also flagged."

### 5.3 Alert Fatigue

The spectrum expansion roadmap adds nine scanner types. Each produces its own stream of detections. The data fusion system applies cross-source correlation multipliers. Without careful throttling, the system will produce a volume of alerts that overwhelms the user, leading to either anxiety (every notification is a threat) or habituation (notifications are ignored, including real ones).

**Recommendation:** Implement a strict alert budget. No more than 3-5 user-visible alerts per monitoring session, ranked by confidence. Everything else goes to the daily summary. The user can always access the full log, but the system should actively curate what demands the user's attention.

---

## 6. Ethical Framework

### 6.1 Guiding Principles

The following ethical principles should guide CYT-NG's development:

1. **Primum non nocere (first, do no harm).** The tool must not make a victim's situation worse. This means aggressive false positive suppression, trauma-informed communication, and stealth capabilities to prevent discovery by an abuser.

2. **Informed autonomy.** The user should have full control over what the tool does, when it does it, and what it tells them. No silent data collection, no unexpected alerts, no features that activate without explicit consent.

3. **Minimal data retention.** Collect what is needed for detection, retain what is needed for evidence, delete everything else. The system should not become a surveillance archive.

4. **Asymmetric design.** The tool should be architecturally easier to use for defense than for offense. Self-monitoring (detecting things following me) should be the default. Environmental monitoring (logging everything nearby) should require explicit configuration.

5. **Transparency about limitations.** The tool should clearly communicate what it can and cannot detect, its false positive rate, and the fact that a clean scan does not mean the user is not being surveilled (GPS trackers that do not emit RF, visual surveillance, social engineering).

6. **Professional referral.** The tool is not a substitute for law enforcement, legal counsel, or victim advocacy. It should consistently frame itself as one input to a safety plan, not the safety plan itself.

### 6.2 Privacy and Surveillance Tension

CYT-NG exists at a genuine ethical boundary. It necessarily captures information about third parties' devices (MAC addresses, BLE advertisements, TPMS sensor IDs) without their knowledge or consent. This is the same data collection that privacy advocates criticize when performed by corporations or governments.

The ethical distinction is purpose and power differential. A stalking victim scanning for AirTags in their vehicle is not morally equivalent to a corporation tracking customers through a retail store, even though the underlying technology is identical. The ethical framework should acknowledge this tension explicitly:

- The tool collects third-party data as a necessary side effect of self-protection.
- This data should be retained for the minimum time necessary.
- This data should never be shared, sold, or used for any purpose other than the user's safety.
- The tool should not facilitate identification of third parties beyond what is necessary for threat assessment.

### 6.3 Law Enforcement Recommendations

The question of whether CYT-NG should recommend contacting law enforcement is genuinely difficult.

**Arguments for:**
- Law enforcement has investigative powers the user does not.
- A formal report creates a legal record that may be important later.
- In many jurisdictions, stalking is a criminal offense and reporting is the first step toward legal protection.

**Arguments against:**
- In some cases, law enforcement personnel are the surveillants (the documentation's ADS-B aircraft tracking feature explicitly references FBI and DHS surveillance flights).
- Law enforcement response to stalking reports is notoriously inconsistent, with many victims reporting that police dismissed their concerns or declined to investigate.
- In communities with adversarial relationships to police (communities of color, undocumented immigrants, LGBTQ+ individuals), a law enforcement recommendation may be unwelcome or dangerous.
- Filing a report may escalate the situation if the abuser learns of it.

**Recommendation:** The system should present law enforcement as one option among several, never as the default or primary recommendation. The language should be: "You may choose to share this information with law enforcement, a domestic violence advocate, a trusted attorney, or a trusted person in your life. [Links to each resource type]." The system should never automatically contact law enforcement or any third party. The user must retain complete control over who learns about their situation.

For the specific case of law enforcement surveillance (IMSI catchers, aerial platforms), the system should present findings factually ("An aircraft matching a known government registration has been detected circling this area") without recommending any specific action. The user's response to government surveillance is a political and personal decision that the tool should not attempt to direct.

### 6.4 Responsible Disclosure of Capabilities

The project documentation is remarkably detailed about detection methodologies. This transparency is valuable for open-source credibility but also serves as an evasion manual. A surveiller who reads the spectrum expansion roadmap knows exactly which signals CYT-NG can and cannot detect, which allows them to select surveillance methods that fall outside its detection envelope.

This is an inherent tension in open-source security tools and does not have a clean resolution. The benefit of open-source transparency (community review, trust, improvement) likely outweighs the cost of capability disclosure, since sophisticated surveillers already understand RF detection principles. However, the project should be aware that its documentation is dual-use and should avoid publishing specific evasion guidance (e.g., "the system cannot detect X" statements that function as recommendations).

---

## Summary of Recommendations

| Area | Recommendation | Priority |
|------|---------------|----------|
| Alert defaults | Daily summary mode as default; real-time alerts opt-in | High |
| False positive suppression | Minimum 0.7 threshold for user-visible alerts; require multi-source corroboration | High |
| Alert language | Calm, factual, no intent attribution; graduated urgency scale | High |
| Resource integration | Embed DV hotlines and safety resources in all alert flows | High |
| Stealth mode | Hidden UI, encrypted storage, obfuscated file names, duress password | High |
| Data retention | Auto-delete non-flagged data after 48 hours | Medium |
| Ethical use statement | First-run display with substantive explanation of intended use | Medium |
| Self-monitoring default | Default to "detecting things following me" not "logging everything nearby" | Medium |
| Alert budget | Maximum 3-5 alerts per session; rest in daily summary | Medium |
| No community features | Provide links to professional resources instead | Medium |
| Law enforcement framing | Present as one option among several; never auto-contact | Medium |
| Forensic export controls | Require explicit action; log exports; include metadata watermark | Low |
| Uncertainty communication | Natural language confidence levels, not raw scores | Low |
| Session scheduling | Allow time-bounded monitoring windows | Low |

---

## References

- Blanchette, I., & Richards, A. (2010). The influence of affect on higher level cognition: A review of research on interpretation, judgement, decision making and reasoning. *Cognition & Emotion*, 24(4), 561-595.
- Freed, D., Palmer, J., Minchala, D., Levy, K., Ristenpart, T., & Dell, N. (2017). Digital technologies and intimate partner violence: A qualitative analysis with multiple stakeholders. *Proceedings of the ACM on Human-Computer Interaction*, 1(CSCW), 1-22.
- Kimble, M., Boxwala, M., Bean, W., Maletsky, K., Halper, J., Spollen, K., & Fleming, K. (2014). The impact of hypervigilance: Evidence for a forward feedback loop. *Journal of Anxiety Disorders*, 28(2), 241-245.
- LeDoux, J. E. (1996). *The Emotional Brain: The Mysterious Underpinnings of Emotional Life*. Simon & Schuster.
- Moscovici, S., & Zavalloni, M. (1969). The group as a polarizer of attitudes. *Journal of Personality and Social Psychology*, 12(2), 125-135.
- National Network to End Domestic Violence. (2024). *Technology Safety and Surveillance Survey*. techsafety.org.
