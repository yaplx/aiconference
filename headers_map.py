# ==============================================================================
# 1. HEADER MAPPING CONFIGURATION
# ==============================================================================
HEADER_MAP = {
    # --- Front Matter ---
    "ABSTRACT": "ABSTRACT",
    "ABBREVIATIONS": "PREAMBLE",

    # --- Intro & Background ---
    "INTRODUCTION": "INTRODUCTION",
    "RELATED WORK": "RELATED WORK",
    "LITERATURE REVIEW": "RELATED WORK",
    "BACKGROUND": "RELATED WORK",

    # --- Methods (IMRAD: M) ---
    "METHOD": "METHOD",
    "METHODS": "METHOD",
    "METHODOLOGY": "METHOD",
    "MATERIALS AND METHODS": "METHOD",
    "PROPOSED METHOD": "METHOD",
    "PROPOSED APPROACH": "METHOD",

    # --- Experiments / Evaluation ---
    "EXPERIMENT": "EXPERIMENT",
    "EXPERIMENTS": "EXPERIMENT",
    "EXPERIMENTAL SETUP": "EXPERIMENT",
    "EVALUATION": "EXPERIMENT",
    "PERFORMANCE EVALUATION": "EXPERIMENT",

    # --- Results (IMRAD: R) ---
    "RESULT": "RESULT",
    "RESULTS": "RESULT",
    "FINDINGS": "RESULT",

    # --- Discussion (IMRAD: D) ---
    "DISCUSSION": "DISCUSSION",
    "DISCUSSIONS": "DISCUSSION",
    "STRENGTHS AND LIMITATIONS": "DISCUSSION",
    "LIMITATIONS": "DISCUSSION",

    # --- Conclusion & Future Work ---
    "CONCLUSION": "CONCLUSION",
    "CONCLUSIONS": "CONCLUSION",
    "CONCLUDING REMARKS": "CONCLUSION",
    "SUMMARY": "CONCLUSION",
    "CONCLUSION AND FUTURE WORK": "CONCLUSION",
    "FUTURE WORK": "CONCLUSION",

    # --- Back Matter ---
    "REFERENCES": "REFERENCES",
    "BIBLIOGRAPHY": "REFERENCES",
    "ACKNOWLEDGMENT": "ACKNOWLEDGMENT",
    "ACKNOWLEDGEMENTS": "ACKNOWLEDGMENT",
    "APPENDIX": "APPENDIX",
    "APPENDICES": "APPENDIX",
    "DECLARATION": "DECLARATION",
    "ETHICS APPROVAL AND CONSENT TO PARTICIPATE": "DECLARATION",
    "CONSENT FOR PUBLICATION": "DECLARATION",
    "AVAILABILITY OF DATA AND MATERIALS": "DECLARATION",
    "COMPETING INTERESTS": "DECLARATION",
    "FUNDING": "DECLARATION",
    "AUTHORS' CONTRIBUTIONS": "DECLARATION",
    "FIGURE LEGENDS": "APPENDIX",
    "TABLE LEGENDS": "APPENDIX"
}

# ==============================================================================
# 2. SECTION ROUTING (THE "PODS")
# ==============================================================================

# Front Matter is used strictly for the "First Pass" (Relevance Check)
FRONT_MATTER = ["ABSTRACT", "PREAMBLE"]

# Back Matter is completely ignored by the detailed AI reviewer
BACK_MATTER = ["REFERENCES", "ACKNOWLEDGMENT", "APPENDIX", "DECLARATION"]

# POD 1: The Setup (Sent to the AI together)
POD_1 = ["INTRODUCTION", "RELATED WORK", "METHOD"]

# POD 2: The Execution & Findings (Sent to the AI together)
POD_2 = ["EXPERIMENT", "RESULT", "DISCUSSION", "CONCLUSION"]