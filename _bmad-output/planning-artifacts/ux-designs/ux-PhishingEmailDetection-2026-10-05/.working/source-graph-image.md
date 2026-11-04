# Direct visual extract: Graph_IAP419t

2026-10-05. The user-supplied [Graph image](../imports/graph-iap419t.png), titled **EMAIL THREAT DETECTION / SYSTEM ARCHITECTURE**, was directly inspected. It is an unchanged import of `C:/Users/PC/Downloads/Graph_IAP419t.drawio (1).png`; the import record reports identical SHA256 `A5649657FE85867616CE388389F958DEEB439BAD8066AE11B46D6D18E82C911E` for source and copy. This supersedes the earlier missing-image evidence gap without rewriting the historical extract.

## Visible image facts

- **Input:** a user submits email in `.eml` format.
- **Preprocessing:** Parse email with a MIME parser (`Python: email / mailbox`), followed by Clean text with Regex/NLP. Cleaning operations shown are Tokenize, Lowercase, Stopwords and HTML removal.
- **Feature Fusion:** the Parse email output feeds **40 Structural features** directly, while Clean text feeds a **Text vector / Doc2Vec / Gensim** branch. Both feed **Concatenate / One feature vector**. Structural groups shown are Content, URLs, Headers, HTML, Attachments and Social cues.
- **Classification:** **Trained model / Best selected classifier** feeds **Predict**, with Class label and Probability indicated. The picture does not explicitly depict a fitted scaler or specify concatenation order.
- **Results:** Threat prediction shows **Legitimate, Spam, Phishing** and Probability score. Detected indicators include Suspicious URL and Urgent wording. Email inspector offers Headers, URLs, Files and HTML.
- **Offline Training:** Enron → Legitimate, Nazario → Phishing and SpamAssassin → Spam feed Preprocess & split, then Train / Validation / Test-evaluate and Compare → select. Candidate names shown are XGBoost, RF, SVM and MLP / …. A dashed handoff sends the trained model to Classification.
- **Web Application:** Frontend ↔ Backend API (`Flask / FastAPI`) ↔ **Model + results storage**. Arrow styles distinguish analysis flow from trained-model handoff.

## Current UX interpretation and boundaries

The image is an architectural input, not a UI mockup or approval of colors/layout. A3/A4 visual assumptions remain unchanged. Latest intake and the [updated plan](../../../../../docs/IAP_Web_Application_Plan.md) govern the manual, explicit-Analyze, English MVP: successful output is exactly **Legit** or **Phishing**; request failures remain operational states. Probability, indicators and inspector are deferred rather than copied into the MVP.

The raw engineered-feature branch before cleaning is consistent with project requirements. The fitted scaler, **Doc2Vec followed by scaled engineered features** and same-run/release artifact requirement come from the [project instructions](../../../../../AGENTS.md) and plan §4.2, not from explicit scaler/order annotations in the image.

The diagram's three corpus/class labels and best-classifier comparison are reference architecture. They do not prove that a current release has a phishing-only target, that any named classifier is selected, or that training/validation/evaluation ran as pictured. The eligible-release gate remains in force; mixed spam/phishing positives cannot be renamed Phishing. Results remain transient browser-session state with no MVP database/server history, while verified model artifacts require storage. Actual prediction, performance, deployment, privacy retention and cleanup are not certified by viewing or importing this picture.

Current decisions are distilled into [DESIGN.md](../DESIGN.md), [EXPERIENCE.md](../EXPERIENCE.md) and [final source reconciliation](../reconcile-plan-graph.md). No source image, plan, PRD or spec was modified.
