from langchain.tools import tool

from job_tools.memory_store import (
    add_job_preference,
    add_company_feedback,
    add_role_feedback,
    add_job_feedback,
    delete_memory_item,
    get_last_target_industry,
    load_memory,
    memory_as_text,
    set_last_target_industry,
)


def _tool_log(name: str) -> None:
    print(f"TOOL: {name}")


@tool
def remember_job_preference(preference: str) -> dict:
    """
    Remember a general job-search preference from the user.
    Use this when the user says things like:
    'remember that I do not want help desk jobs'
    or 'from now on prioritize backend roles'.
    """

    _tool_log("remember_job_preference")
    item = add_job_preference(preference)

    return {
        "status": "remembered",
        "memory_type": "job_preference",
        "item": item
    }


@tool
def remember_company_feedback(company: str, feedback: str) -> dict:
    """
    Remember feedback about a specific company.
    Use this when the user gives company-specific instructions or opinions.
    """

    _tool_log("remember_company_feedback")
    item = add_company_feedback(company=company, feedback=feedback)

    return {
        "status": "remembered",
        "memory_type": "company_feedback",
        "item": item
    }


@tool
def remember_role_feedback(role_or_keyword: str, feedback: str) -> dict:
    """
    Remember feedback about a role type, keyword, technology, or job category.
    Use this when the user says a certain role or skill should be prioritized or avoided.
    """

    _tool_log("remember_role_feedback")
    item = add_role_feedback(role_or_keyword=role_or_keyword, feedback=feedback)

    return {
        "status": "remembered",
        "memory_type": "role_feedback",
        "item": item
    }


@tool
def remember_job_feedback(
    job_id: str,
    title: str,
    company: str,
    feedback: str
) -> dict:
    """
    Remember feedback about a specific job that appeared in a report.
    Use this when the user says a specific job was a good or bad match.
    """

    _tool_log("remember_job_feedback")
    item = add_job_feedback(
        job_id=job_id,
        title=title,
        company=company,
        feedback=feedback
    )

    return {
        "status": "remembered",
        "memory_type": "job_feedback",
        "item": item
    }


@tool
def read_agent_memory() -> dict:
    """
    Read all saved user preferences and feedback memory.
    Use this before scoring jobs or when the user asks what the agent remembers.
    """
    _tool_log("read_agent_memory")

    return {
        "memory": load_memory(),
        "memory_text": memory_as_text()
    }


@tool
def remember_target_industry(target_industry: str) -> dict:
    """
    Remember the most recent target industry.
    Use this after the user names an industry so later searches can reuse it.
    """
    _tool_log("remember_target_industry")
    industry = set_last_target_industry(target_industry)

    return {
        "status": "remembered",
        "target_industry": industry,
    }


@tool
def read_recent_target_industry() -> dict:
    """
    Read the most recently remembered target industry.
    Use this when the user omits the industry for a search request.
    """
    _tool_log("read_recent_target_industry")

    return {
        "found": bool(get_last_target_industry()),
        "target_industry": get_last_target_industry(),
    }


@tool
def forget_memory_item(memory_id: str) -> dict:
    """
    Delete a saved memory item by its memory ID.
    Use this when the user says to forget or remove a specific remembered item.
    """
    _tool_log("forget_memory_item")

    deleted = delete_memory_item(memory_id)

    if deleted is None:
        return {
            "status": "not_found",
            "memory_id": memory_id
        }

    return {
        "status": "forgotten",
        "memory_id": memory_id,
        "deleted": deleted
    }
