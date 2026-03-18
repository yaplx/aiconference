def get_track_criteria(conference_name):
    """
    Returns specific acceptance criteria based on the selected conference track.
    """
    criteria_map = {
        "C1: AI & Computer Vision - Intelligence Beyond Boundaries":
            "Look for: Novel neural network architectures, image/video processing, generative AI, object detection, or advanced machine learning methodologies.",
        "C2: Quantum Frontiers - Computing, Security & Sensing":
            "Look for: Quantum algorithms, qubit optimization, quantum cryptography (QKD), quantum error correction, or quantum sensors.",
        "C3: Healthcare & Bio-Intelligence - Future of Medicine":
            "Look for: Medical imaging analysis, bioinformatics, personalized medicine, clinical AI applications, or smart health wearables.",
        "C4: Robotics & Autonomous Systems - Machines that Collaborate":
            "Look for: Kinematics, path planning, human-robot interaction (HRI), autonomous vehicles, drones, or swarm robotics.",
        "C5: Intelligent Manufacturing & Industry 5.0 - Human-Machine Synergy":
            "Look for: Digital twins, industrial IoT (IIoT), predictive maintenance, supply chain optimization, or human-in-the-loop production systems.",
        "C6: Embedded Systems & Edge Intelligence - Real-Time, Low-Power Innovation":
            "Look for: Microcontrollers, FPGA designs, low-power machine learning (TinyML), real-time operating systems (RTOS), or edge computing.",
        "C7: Convergence & Society - Ethics, Policy & Global Impact":
            "Look for: AI ethics, regulatory frameworks, data privacy, algorithmic bias, or socio-economic impacts of emerging technologies."
    }
    return criteria_map.get(conference_name, "Ensure the technical content logically aligns with the stated track.")


def get_first_pass_prompt(conference_name, paper_title, abstract_text):
    """
    Returns the prompt for the First Pass (Desk Reject Check).
    """
    return f"""
    You are a reviewer assistant of the conference: "{conference_name}".
    Paper: "{paper_title}"
    Abstract: "{abstract_text[:4000]}"

    Task: Determine strictly if the paper is RELEVANT to the conference topic.

    **STRICT GUIDELINES:**
    1. **NEUTRALITY:** Maintain a strictly neutral and objective tone.
    2. **READ-ONLY:** Do NOT modify, rewrite, or correct the abstract content.
    3. **NO MARKDOWN:** Do not use bolding (**text**) or italics (*text*).

    Criteria for REJECT:
    - Irrelevant: Topic is clearly outside the scope of {conference_name}.
    - (Ignore novelty or structure issues for this check - ONLY check relevance).

    OUTPUT FORMAT:
    Option 1 (If Irrelevant):
    DECISION: REJECT
    REASON: The paper is not relevant to the conference theme.

    Option 2 (If Relevant):
    DECISION: PROCEED
    """


def get_section_focus(clean_name):
    """
    Determines the specific review focus and common mistakes based on the section name.
    """
    if "METHOD" in clean_name:
        return """Focus: Reproducibility and mathematical soundness.
    COMMON MISTAKES TO CHECK:
    - Lack of reproducibility details (missing parameters, setup specifics, or dataset details).
    - Mathematical unsoundness, undefined variables, or unexplained equations.
    - Unclear algorithm steps, missing pseudocode, or vague architecture descriptions."""

    elif "EXPERIMENT" in clean_name or "RESULT" in clean_name:
        return """Focus: Fairness, statistical significance, and data claims.
    COMMON MISTAKES TO CHECK:
    - Unfair, outdated, or completely missing baselines for comparison.
    - Lack of statistical significance, confidence intervals, or error metrics.
    - Exaggerated claims in the text that do not logically match the data/results shown."""

    elif "INTRO" in clean_name:
        return """Focus: Clarity of the research gap and problem statement.
    COMMON MISTAKES TO CHECK:
    - Failing to clearly identify and state the exact research gap.
    - Missing or vague explicit contribution statements.
    - Lack of clear motivation or context for why the problem matters."""

    elif "RELATED" in clean_name or "LITERATURE" in clean_name or "BACKGROUND" in clean_name:
        return """Focus: Coverage of recent state-of-the-art works and differentiation.
    COMMON MISTAKES TO CHECK:
    - Missing recent state-of-the-art works (e.g., completely ignoring papers from the last 3 years).
    - Merely listing/summarizing papers without actively comparing or contrasting them to the proposed work.
    - Unclear differentiation between existing limitations and the current paper's novel solution."""

    elif "DISCUSSION" in clean_name or "CONCLUSION" in clean_name:
        return """Focus: Validity of conclusions and acknowledgment of limitations.
    COMMON MISTAKES TO CHECK:
    - Making sweeping claims or broad conclusions that are not directly supported by the experiments presented.
    - Ignoring or purposefully omitting the limitations and constraints of the proposed method.
    - Simply copy-pasting or repeating the abstract without synthesizing the actual findings."""

    return """Focus: General academic rigor and clarity.
    COMMON MISTAKES TO CHECK:
    - Unclear logical flow or poor structural organization.
    - Claims made without adequate citation or evidence."""


def get_batch_review_prompt(conference_name, paper_title, sections_info):
    """
    Generates a prompt for reviewing MULTIPLE sections at once for shared context,
    but demands XML-tagged outputs to separate the feedback.
    """
    track_specifics = get_track_criteria(conference_name)

    # Compile the sections text into a single context block
    compiled_sections = ""
    for sec in sections_info:
        compiled_sections += f"\n\n====================\nSECTION TITLE: {sec['title']}\nSECTION FOCUS:\n{sec['focus']}\n\nTEXT:\n{sec['content'][:15000]}\n====================\n"

    return f"""
    SYSTEM ROLE:
    You are a strict, objective conference reviewer assistant. 

    CONTEXT:
    Conference Track: "{conference_name}"
    Paper Title: "{paper_title}"

    TRACK ALIGNMENT EXPECTATIONS:
    {track_specifics}

    TASK:
    You are being provided with a group of related sections from the paper below. Read ALL of them to understand the full context (e.g., if data is missing in "Results" but explained in "Experiments", do NOT flag it as an error).

    After reading the context, you must generate a SEPARATE review for EACH section. 
    Cross-reference each section strictly against its listed "SECTION FOCUS" mistakes, AND ensure the technical details align with the "TRACK ALIGNMENT EXPECTATIONS".

    CRITICAL APPROVAL RULE: If a section does NOT exhibit the common mistakes and aligns with the track, you MUST approve it without suggestions. Do not invent issues. 

    CRITICAL FORMATTING RULES:
    1. PLAIN TEXT ONLY: You must not use any Markdown formatting. Do not use asterisks, bolding, italics, or headers inside the review.
    2. SPELL OUT SYMBOLS: You must spell out all Greek letters and mathematical symbols.
    3. LIMITATIONS: Maximum 4 critical points per section. Keep points short and direct.
    4. XML WRAPPING: You MUST wrap the review for EACH section inside <REVIEW> tags. Provide the exact section title in the attribute.

    OUTPUT TEMPLATE (Repeat for EACH section provided):

    <REVIEW section="Exact Section Title">
    STATUS: [ACCEPT / ACCEPT WITH SUGGESTIONS]

    FLAGGED ISSUES:
    - [Point 1]
    - [Point 2]
    </REVIEW>

    (Note: If the STATUS is ACCEPT, omit the FLAGGED ISSUES header entirely. Do not write "None".)

    HERE ARE THE SECTIONS TO REVIEW:
    {compiled_sections}
    """