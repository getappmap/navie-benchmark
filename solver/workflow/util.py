from typing import Optional

MAX_TOTAL_CONTEXT = 16_000


def context_to_xml(context: Optional[dict[str, str]]) -> Optional[str]:
    if not context:
        return None
    result = ""
    for k, v in context.items():
        this = f"""<code-snippet location="{k}"><![CDATA[{v}
]]></code-snippet>
"""
        if len(result) + len(this) > MAX_TOTAL_CONTEXT:
            break
        result += this
    return result
