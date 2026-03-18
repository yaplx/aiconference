def get_track_criteria(conference_name):
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


def get_first_pass_prompt(conference_name, paper_title, abstract_text, audience):
    persona = "strict, objective reviewer assistant reporting to the committee" if audience == "reviewer" else "constructive peer reviewer addressing the author"

    return f"""
    You are a {persona} for the conference: "{conference_name}".
    Paper: "{paper_title}"
    Abstract: "{abstract_text[:4000]}"

    Task: Determine strictly if the paper is RELEVANT to the conference topic.

    **STRICT GUIDELINES:**
    1. **NEUTRALITY:** Maintain a professional and objective tone.
    2. **READ-ONLY:** Do NOT modify, rewrite, or correct the abstract content.
    3. **NO MARKDOWN:** Do not use bolding (**text**) or italics (*text*).

    Criteria for REJECT:
    - Irrelevant: Topic is clearly outside the scope of {conference_name}.

    OUTPUT FORMAT:
    Option 1 (If Irrelevant):
    DECISION: REJECT
    REASON: The paper is not relevant to the conference theme. [Provide brief reasoning].

    Option 2 (If Relevant):
    DECISION: PROCEED
    """


def get_section_focus(clean_name, audience):
    if audience == "reviewer":
        header = "COMMON MISTAKES TO CHECK:"
        method_focus = "- Lack of reproducibility details.\n- Mathematical unsoundness.\n- Unclear algorithm steps."
        result_focus = "- Unfair or missing baselines.\n- Lack of statistical significance.\n- Exaggerated claims."
        intro_focus = "- Failing to identify the exact research gap.\n- Missing explicit contributions."
        related_focus = "- Missing recent state-of-the-art works (last 3 years).\n- Merely listing papers without contrasting."
        discuss_focus = "- Making sweeping claims not supported by data.\n- Ignoring limitations."
        default_focus = "- Unclear logical flow.\n- Claims without citation."
    else:
        header = "AREAS FOR CONSTRUCTIVE FEEDBACK:"
        method_focus = "- Advise adding missing reproducibility details (parameters, dataset specs).\n- Point out undefined variables or equations.\n- Suggest clarifying algorithm steps or adding pseudocode."
        result_focus = "- Suggest adding baselines if missing.\n- Recommend adding statistical significance or error metrics.\n- Advise toning down exaggerated claims to match the data."
        intro_focus = "- Recommend clarifying the exact research gap.\n- Suggest making contribution statements more explicit."
        related_focus = "- Advise including more recent state-of-the-art works.\n- Suggest explicitly contrasting existing works with the proposed method."
        discuss_focus = "- Advise narrowing claims to strictly what the experiments support.\n- Suggest explicitly discussing the limitations of the method."
        default_focus = "- Suggest improvements for logical flow.\n- Point out claims that need proper citations."

    if "METHOD" in clean_name:
        return f"Focus: Reproducibility and mathematical soundness.\n{header}\n{method_focus}"
    elif "EXPERIMENT" in clean_name or "RESULT" in clean_name:
        return f"Focus: Fairness, statistical significance, and data claims.\n{header}\n{result_focus}"
    elif "INTRO" in clean_name:
        return f"Focus: Clarity of the research gap and problem statement.\n{header}\n{intro_focus}"
    elif "RELATED" in clean_name or "LITERATURE" in clean_name or "BACKGROUND" in clean_name:
        return f"Focus: Coverage of recent works and differentiation.\n{header}\n{related_focus}"
    elif "DISCUSSION" in clean_name or "CONCLUSION" in clean_name:
        return f"Focus: Validity of conclusions and limitations.\n{header}\n{discuss_focus}"

    return f"Focus: General academic rigor and clarity.\n{header}\n{default_focus}"


def get_batch_review_prompt(conference_name, paper_title, sections_info, audience):
    track_specifics = get_track_criteria(conference_name)

    compiled_sections = ""
    for sec in sections_info:
        compiled_sections += f"\n\n====================\nSECTION TITLE: {sec['title']}\nSECTION FOCUS:\n{sec['focus']}\n\nTEXT:\n{sec['content'][:15000]}\n====================\n"

    if audience == "reviewer":
        persona = "strict, objective conference reviewer assistant."
        status_options = "[ACCEPT / ACCEPT WITH SUGGESTIONS]"
        issues_header = "FLAGGED ISSUES:"
        approval_rule = "If a section does NOT exhibit the common mistakes, you MUST approve it without suggestions."
    else:
        persona = "constructive, professional peer reviewer speaking directly to the paper's author."
        status_options = "[MEETS DESK REQUIREMENTS / REVISIONS RECOMMENDED]"
        issues_header = "SUGGESTED REVISIONS:"
        approval_rule = "If a section is strong and requires no major revisions, you MUST approve it without suggestions. Address the author directly (e.g., 'Consider adding...')."

    return f"""
    SYSTEM ROLE:
    You are a {persona}

    CONTEXT:
    Conference Track: "{conference_name}"
    Paper Title: "{paper_title}"

    TRACK ALIGNMENT EXPECTATIONS:
    {track_specifics}

    TASK:
    You are being provided with a group of related sections from the paper below. Read ALL of them to understand the full context.

    After reading, generate a SEPARATE review for EACH section. 
    Cross-reference each section strictly against its listed "SECTION FOCUS", AND ensure the technical details align with the "TRACK ALIGNMENT EXPECTATIONS".

    CRITICAL APPROVAL RULE: {approval_rule}

    CRITICAL FORMATTING RULES:
    1. PLAIN TEXT ONLY: You must not use any Markdown formatting.
    2. SPELL OUT SYMBOLS: You must spell out all Greek letters and mathematical symbols.
    3. LIMITATIONS: Maximum 4 bullet points per section. Keep points short and direct.
    4. XML WRAPPING: You MUST wrap the review for EACH section inside <REVIEW> tags. Provide the exact section title in the attribute.

    OUTPUT TEMPLATE (Repeat for EACH section provided):

    <REVIEW section="Exact Section Title">
    STATUS: {status_options}

    {issues_header}
    - [Point 1]
    - [Point 2]
    </REVIEW>

    (Note: If the STATUS is ACCEPT or MEETS DESK REQUIREMENTS, omit the {issues_header} entirely. Do not write "None".)

    HERE ARE THE SECTIONS TO REVIEW:
    {compiled_sections}
    """