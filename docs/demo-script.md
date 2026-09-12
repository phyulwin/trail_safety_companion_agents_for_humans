# Trail demo video — four-minute recording script

Record the locally running app with `TRAIL_AGENT_MODE=mock` for reproducibility, clearly identify the simulated scenario, and show the separately verified Bedrock option when explaining architecture; do not present the deterministic provider as live model reasoning.

## Before recording

Start both servers, open the frontend at desktop width, run and end a normal demo once to populate history, then ensure no active Trail remains; have the Following and Community preview buttons ready, and keep all account details synthetic.

## 0:00–0:30 — The problem

**Show:** A quiet dashboard with the map and trusted-circle card.

**Narration:** “Going for a run should be a chance to switch off. But when someone goes alone, their family or friends may end up watching a location dot and wondering what every pause means. We built Trail to take on that repetitive monitoring, ask the runner first, and bring the right people into the loop when attention is needed.”

## 0:30–0:50 — The concept

**Show:** Trusted-circle selections, the community toggle, and privacy copy.

**Narration:** “Trail is a personal safety companion, rather than a fitness tracker. The runner chooses who can follow them. Community participation is optional, and nearby helpers receive only an approximate area. Care starts with permission.”

## 0:50–1:40 — Start a live session

**Action:** Click **Run safety demo** around 1:10, allowing the server-driven movement to begin.

**Show:** The route, motion status, risk estimate, and signal readouts.

**Narration:** “For this demonstration, a laptop simulates a run in Pasadena. These environmental signals and route alternatives are labelled simulated. What happens next is real application behavior: FastAPI records the sensor events, SQLAlchemy stores the route, and WebSockets update the interface. Movement begins normally, then our simulated corridor becomes more isolated and the runner stops.”

## 1:40–2:40 — Evidence, check-in, escalation

**Show:** The check-in modal, let its fifteen-second countdown expire, then scroll to the persisted timeline.

**Narration:** “Trail's statistical detector compares pace with its moving baseline and considers the length of the stop. The Strands safety agent receives structured evidence and chooses tools within deterministic rules. It checks in before escalating. The runner can say ‘I'm OK’ or ask for help. Here we leave the check-in unanswered, so the server deadline creates a trusted-contact in-app alert. The timeline explains the evidence, the selected action, and why it was permitted.”

**Action:** Open **Following**, then **Preview demo recipients**.

**Narration:** “This is the sample contact's view, previewed by the demo owner. Contacts can follow only sessions explicitly shared with them. This MVP creates in-app alerts; it does not call emergency services or send SMS.”

## 2:40–3:10 — Community assistance

**Action:** Open **Community**, retaining or enabling the simulated recipient preview.

**Show:** The approximate area and one available helper.

**Narration:** “Because the runner enabled the community network and the escalation rules passed, Trail evaluates five simulated verified helpers nearby. One becomes available. The community sees this broad zone, without the runner's name, route, or exact coordinates. Accepting the request does not unlock a precise location.”

## 3:10–3:30 — Lost-item backtracking

**Action:** Open **Trail history**, select a previous route, enter “keys,” and choose **Find possible search points**.

**Narration:** “Trail also keeps the last ten days of private routes. If you lose your keys, it highlights possible search locations based on pauses, sudden slowdowns, turns, and your bookmarks. These are starting points for a search, not a claim that the app knows where an item was lost.”

## 3:30–4:00 — Architecture and close

**Show:** The Mermaid architecture and the small Bedrock validation report, with no credentials on screen.

**Narration:** “At the center is a genuine Strands agent with twelve custom tools. The reproducible demo uses a deterministic model inside the real SDK loop, and the Amazon Bedrock path has also been tested on synthetic state. Policies constrain every action, and a fallback preserves check-in deadlines if inference fails. Trail belongs in Good Neighbor Agents because it connects a runner, a trusted circle, and a privacy-preserving community. Run freely. Trail watches your back.”

## Alternate normal-path clip

End the active session and choose **Or try a normal run**; record the shorter stop, automatic simulated OK response, and resolved event without a contact alert, then use this clip if judges want to see how Trail avoids unnecessary escalation.
