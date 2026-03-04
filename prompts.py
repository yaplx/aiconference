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
        
        {section_focus}
        
        TASK:
    Identify critical issues in the provided text that require manual verification by a human expert. Cross-reference the text strictly against the "COMMON MISTAKES" listed above.
    
    CRITICAL APPROVAL RULE: If the section does NOT exhibit the common mistakes listed above and has no other major structural issues, you MUST approve the section without suggestions. 
    Do not invent issues. By default, all diagrams and figures will be checked manually.
        
        STRICT RULES:
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