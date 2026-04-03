import re
import prompts
from openai import OpenAI


def get_openai_client(api_key):
    return OpenAI(api_key=api_key)


def evaluate_first_pass(client, paper_title, abstract_text, conference_name, audience):
    prompt = prompts.get_first_pass_prompt(conference_name, paper_title, abstract_text, audience)
    response = client.chat.completions.create(model="gpt-5", messages=[{"role": "user", "content": prompt}])
    return response.choices[0].message.content


def generate_batch_review(client, sections_list, paper_title, conference_name, audience):
    if not sections_list: return {}
    sections_info = []
    for sec in sections_list:
        clean_name = re.sub(r"^[\d\w]+\.\s*", "", sec['title'].upper().strip())
        focus = prompts.get_section_focus(clean_name, audience)
        sections_info.append({"title": sec['title'], "focus": focus, "content": sec['content']})

    prompt = prompts.get_batch_review_prompt(conference_name, paper_title, sections_info, audience)
    response = client.chat.completions.create(model="gpt-5", messages=[{"role": "user", "content": prompt}])
    raw_output = response.choices[0].message.content

    xml_results = {}
    pattern = re.compile(r'<REVIEW\s+section=["\']?(.*?)["\']?>(.*?)</REVIEW>', re.IGNORECASE | re.DOTALL)
    for match_title, feedback in pattern.findall(raw_output):
        xml_results[match_title.strip().upper()] = feedback.strip()

    final_results = {}
    for sec in sections_list:
        title_upper = sec['title'].strip().upper()
        content = next((v for k, v in xml_results.items() if k in title_upper or title_upper in k),
                       "AI failed to format feedback.")
        final_results[sec['title']] = content
    return final_results