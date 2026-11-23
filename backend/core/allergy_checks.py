from typing import Iterable, List, Optional


def parse_patient_allergies(raw_allergies: Optional[str]) -> List[str]:
    if not raw_allergies:
        return []
    parts = []
    for chunk in raw_allergies.replace(";", ",").replace("\n", ",").split(","):
        cleaned = chunk.strip().lower()
        if cleaned:
            parts.append(cleaned)
    return parts


def find_allergy_conflicts(
    *,
    raw_allergies: Optional[str],
    medicine_names: Iterable[str],
    salt_compositions: Iterable[str] = (),
) -> List[str]:
    """
    Returns human-readable conflict messages when a medicine brand or salt
    matches a patient's recorded allergies.
    """
    allergens = parse_patient_allergies(raw_allergies)
    if not allergens:
        return []

    targets = [
        (label.strip(), label.strip().lower())
        for label in list(medicine_names) + list(salt_compositions)
        if label and label.strip()
    ]
    conflicts: List[str] = []
    for allergen in allergens:
        for original_label, lowered_target in targets:
            if allergen in lowered_target or lowered_target in allergen:
                msg = f"Allergy match for '{allergen}' against '{original_label}'"
                if msg not in conflicts:
                    conflicts.append(msg)
    return conflicts