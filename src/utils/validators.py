"""WRD API — XML and Wazuh rule validators."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List
from xml.etree import ElementTree as ET


async def validate_xml_files(base_path: Path) -> Dict[str, Any]:
    """
    Validate XML syntax of all .xml files under base_path.
    Returns a report with counts of valid/invalid files.
    """
    valid: List[str] = []
    errors: List[Dict[str, str]] = []

    xml_files = list(base_path.rglob("*.xml"))

    if not xml_files:
        return {
            "valid": True,
            "files_checked": 0,
            "valid_count": 0,
            "error_count": 0,
            "errors": [],
            "message": "No XML files found in repository.",
        }

    for file_path in xml_files:
        try:
            ET.parse(str(file_path))
            valid.append(str(file_path.relative_to(base_path)))
        except ET.ParseError as e:
            errors.append(
                {
                    "file": str(file_path.relative_to(base_path)),
                    "error": str(e),
                }
            )

    return {
        "valid": len(errors) == 0,
        "files_checked": len(xml_files),
        "valid_count": len(valid),
        "error_count": len(errors),
        "errors": errors,
        "message": "All files valid." if not errors else f"{len(errors)} file(s) have XML errors.",
    }


def validate_wazuh_rule_element(element: ET.Element) -> List[str]:
    """
    Basic semantic validation of a Wazuh <rule> XML element.
    Returns a list of warnings/errors found.
    """
    issues: List[str] = []

    rule_id = element.get("id")
    if not rule_id:
        issues.append("Rule missing 'id' attribute")
    else:
        try:
            rid = int(rule_id)
            if rid < 100 or rid > 999999:
                issues.append(f"Rule id {rid} out of valid range (100-999999)")
        except ValueError:
            issues.append(f"Rule id '{rule_id}' is not an integer")

    level = element.get("level")
    if level:
        try:
            lvl = int(level)
            if lvl < 0 or lvl > 15:
                issues.append(f"Rule level {lvl} out of valid range (0-15)")
        except ValueError:
            issues.append(f"Rule level '{level}' is not an integer")

    # Must have at least one description
    if element.find("description") is None:
        issues.append(f"Rule {rule_id} missing <description> element")

    return issues
