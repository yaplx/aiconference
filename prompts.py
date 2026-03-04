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
    """

def get_section_review_prompt(paper_title, section_name, section_focus, section_text):
    return f"""
        You are a conference reviewer assistant.
        Paper: "{paper_title}"
        Section: "{section_name}"

        Task: 
        Identify critical issues in the provided text that require manual verification by a human expert. Base your review strictly on {section_focus}. 
        Assume all diagrams and figures will be checked manually. If there are no major issues, you must approve the section.
        
        **STRICT RULES:**
        1. **NO MODIFICATION:** Do NOT attempt to rewrite, fix, or modify the data/text. Only review it.
        2. **NEUTRALITY:** Be objective. Do not praise. Only raise verification points. It is ok to skip if there is none.
        3. **NO GREEK/MATH SYMBOLS:** You MUST SPELL OUT all Greek letters and symbols. 
        4. **NO MARKDOWN:** Do NOT use markdown bolding (like **text**) or headers.
        5. **LIMIT:** Maximum 4 critical points.
        6. **CONCISENESS:** Keep points short, precise, and direct.

        OUTPUT FORMAT:
        STATUS: [ACCEPT / ACCEPT WITH SUGGESTIONS]

        FLAGGED ISSUES:
        - [Point 1]
        - [Point 2]

        (Leave "FLAGGED ISSUES: None" if ACCEPT)

        Section Content:
        {section_text[:15000]}
        """


def get_section_focus(clean_name):
    """
    Determines the specific review focus based on the section name.
    """
    if "METHOD" in clean_name:
        return "Focus on: Reproducibility, mathematical soundness."
    elif "RESULT" in clean_name:
        return "Focus on: Fairness, statistical significance."
    elif "INTRO" in clean_name:
        return "Focus on: Clarity of the research gap."
    elif "RELATED" in clean_name:
        return "Focus on: Coverage of recent state-of-the-art works."
    elif "CONCLUSION" in clean_name:
        return "Focus on: Whether the conclusion is supported by the experiments presented."

    return ""  # Default empty string if no specific focus is needed