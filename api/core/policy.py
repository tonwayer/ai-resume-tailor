from typing import List, Literal, Tuple

def tolerance_profile(t: int) -> Literal["conservative", "balanced", "creative"]:
    if t < 30:
        return "conservative"
    if t < 70:
        return "balanced"
    return "creative"

def policy_for_tolerance(t: int) -> Tuple[Literal["conservative", "balanced", "creative"], List[str], List[str]]:
    mode = tolerance_profile(t)

    if mode == "conservative":
        allowed = [
            "reorder_sections",
            "rewrite_summary_light",
            "rewrite_bullets_light",
            "add_keywords_only_if_already_implied",
        ]
        disallowed = [
            "add_new_roles",
            "add_new_projects",
            "add_metrics_not_in_resume",
            "claim_tools_not_in_resume",
        ]
    elif mode == "balanced":
        allowed = [
            "reorder_sections",
            "rewrite_summary",
            "rewrite_bullets",
            "insert_keywords_into_existing_bullets",
            "add_skills_section_keywords_if_reasonable",
        ]
        disallowed = [
            "add_new_roles",
            "add_new_employers",
            "add_new_degrees",
            "add_new_certifications",
            "invent_metrics",
            "invent_new_technologies",
        ]
    else:
        allowed = [
            "rewrite_summary_strong",
            "rewrite_bullets_strong",
            "expand_bullets_with_reasonable_details",
            "add_skills_keywords_section",
        ]
        disallowed = [
            "add_new_roles",
            "add_new_employers",
            "add_new_degrees",
            "add_new_certifications",
            "invent_metrics_or_specific_numbers",
            "invent_new_technologies",
        ]

    return mode, allowed, disallowed
