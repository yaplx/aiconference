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

    Option 1 (If Relevant):
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

    Task: Identify critical issues that require manual verification by a human expert.

    **STRICT RULES:**
    3. ** GREEK/MATH SYMBOLS:** 
       - CORRECT: α, β, ∑, σ
    output the greek letter in the section text
    OUTPUT FORMAT:
    STATUS: [ACCEPT / ACCEPT WITH SUGGESTIONS]

    FLAGGED ISSUES (Max 4 critical points):
    (Leave empty if ACCEPT)

    Section Content:
    {section_text[:15000]}
    """