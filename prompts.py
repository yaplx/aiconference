def get_first_pass_prompt(conference_name, paper_title, abstract_text):
    """
    Returns the prompt for the First Pass (Desk Reject Check).
    Focus: STRICT RELEVANCE ONLY.
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
    REASON: Topic is relevant to the conference.
    """

def get_section_review_prompt(paper_title, section_name, section_focus, section_text):
    """
    Returns the prompt for the Second Pass (Section Analysis).
    Focus: Critical issues, NO GREEK LETTERS, Max 4 points.
    """
    return f"""
    You are a strictly neutral reviewer assistant.
    Paper: "{paper_title}"
    Section: "{section_name}"

    Task: Identify critical issues that require manual verification by a human expert. {section_focus}

    **STRICT RULES:**
    1. **NO MODIFICATION:** Do NOT attempt to rewrite, fix, or modify the data/text. Only review it.
    2. **NEUTRALITY:** Be objective. Do not praise. Only raise verification points.
    3. **USE GREEK/MATH SYMBOLS:**. 
       - CORRECT: α, β, ∑, σ
        for this list out the greek symbol available in the document
    4. **NO MARKDOWN:** Do NOT use markdown bolding (like **text**) or headers.
    5. **LIMIT:** Maximum 4 critical points.
    6. **CONCISENESS:** Keep points short, precise, and direct.

    **INSTRUCTIONS ON FIGURES & TABLES:**
    1. You cannot see the images.
    2. Raise Clarification: If the text description of a Figure or Table is ambiguous, contradictory, or missing necessary context, explicitly raise a clarification point.

    OUTPUT FORMAT:
    STATUS: [ACCEPT / ACCEPT WITH SUGGESTIONS]

    FLAGGED ISSUES (Max 4 critical points):
    - [Point 1]
    - [Point 2]
    - [Point 3]
    - [Point 4]
    (Leave empty if ACCEPT)

    Section Content:
    {section_text[:15000]}
    """